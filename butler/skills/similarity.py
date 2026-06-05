"""Skill similarity — three-layer funnel (Jaccard → TF-IDF → optional LLM)."""

from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)

LLMFn = Callable[[str], str]


class SimilarityResponseCorrupt(ValueError):
    """Raised when the LLM responded but its reply contains no parseable JSON.

    Distinct from "LLM unreachable" (where ``llm_fn`` itself raises). Corrupt
    responses indicate the provider is up but the model is misbehaving — a
    data-quality signal that callers should surface to /诊断 rather than
    silently treating as "no signal" and falling back to the deterministic
    layer.
    """


class SimilarityLLMUnavailable(RuntimeError):
    """Raised when the LLM provider itself is unreachable.

    Mirrors the consolidator's ``ConsolidatorLLMUnavailable`` (R2-1). The
    exception message carries the underlying cause so the dedup status
    buffer can record *why* the dedup tier was unavailable (network,
    timeout, 401, etc.) — not just the bare fact.
    """


# Audit R2-14: when the LLM tier fails we used to return None and silently
# fall back to the Jaccard/TF-IDF layer, which meant near-duplicate skills
# were treated as distinct and the skill library inflated invisibly. Track
# each degradation event (unavailable vs corrupt) in a bounded buffer so
# /诊断 can detect dedup drift. Same shape as R2-9 / R2-11 / R2-12 / R2-13
# diagnostics buffers.
_MAX_DEDUP_STATUS_ENTRIES = 50
_dedup_status: list[dict[str, Any]] = []


def recent_dedup_status() -> list[dict[str, Any]]:
    """Read the dedup-status diagnostics buffer (test + /诊断 interface)."""
    return list(_dedup_status)


def reset_dedup_status() -> None:
    """Clear the dedup-status diagnostics buffer (test helper)."""
    _dedup_status.clear()


def _record_dedup_status(kind: str, message: str) -> None:
    """Append a dedup degradation event and cap the buffer to its max length."""
    _dedup_status.append({"kind": kind, "message": message})
    if len(_dedup_status) > _MAX_DEDUP_STATUS_ENTRIES:
        del _dedup_status[: len(_dedup_status) - _MAX_DEDUP_STATUS_ENTRIES]

_JIEBA_LOADED = False
_jieba = None


def _ensure_jieba():
    global _JIEBA_LOADED, _jieba
    if not _JIEBA_LOADED:
        try:
            import jieba as jb

            jb.setLogLevel(logging.WARNING)
            _jieba = jb
        except ImportError:
            _jieba = None
        _JIEBA_LOADED = True
    return _jieba


_STOP_WORDS = frozenset(
    [
        "的",
        "了",
        "和",
        "是",
        "在",
        "有",
        "不",
        "这",
        "就",
        "都",
        "也",
        "人",
        "我",
        "他",
        "她",
        "你",
        "们",
        "对",
        "个",
        "被",
        "到",
        "可以",
        "或",
        "等",
        "但",
        "如果",
        "那",
        "the",
        "a",
        "an",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "and",
        "or",
        "but",
        "not",
        "this",
        "that",
        "it",
        "as",
    ]
)


def trigger_jaccard(triggers_a: list[str], triggers_b: list[str]) -> float:
    """Jaccard similarity on trigger keyword sets, in [0, 1]."""
    if not triggers_a or not triggers_b:
        return 0.0
    set_a = {t.strip().lower() for t in triggers_a if str(t).strip()}
    set_b = {t.strip().lower() for t in triggers_b if str(t).strip()}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _skill_text(skill: dict[str, Any]) -> str:
    desc = str(skill.get("description", "") or "")
    body = str(skill.get("content", skill.get("body", "")) or "")
    return f"{desc}\n{body}"


def _tokenize(text: str) -> list[str]:
    jb = _ensure_jieba()
    if jb is not None:
        tokens = list(jb.cut(text))
    else:
        tokens = re.findall(r"[\u4e00-\u9fff]+|[a-zA-Z]+", text.lower())
    out: list[str] = []
    for t in tokens:
        s = t.strip().lower()
        if s and len(s) > 1 and s not in _STOP_WORDS:
            out.append(s)
    return out


def _build_tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    n_docs = len(docs)
    if n_docs == 0:
        return []
    df: Counter[str] = Counter()
    for doc in docs:
        for t in set(doc):
            df[t] += 1
    vectors: list[dict[str, float]] = []
    for doc in docs:
        tf: Counter[str] = Counter(doc)
        total = len(doc) if doc else 1
        vec: dict[str, float] = {}
        for term, count in tf.items():
            idf = math.log((n_docs + 1) / (df.get(term, 0) + 1)) + 1
            vec[term] = (count / total) * idf
        vectors.append(vec)
    return vectors


def _cosine_similarity(vec_a: dict[str, float], vec_b: dict[str, float]) -> float:
    if not vec_a or not vec_b:
        return 0.0
    common = set(vec_a) & set(vec_b)
    if not common:
        return 0.0
    dot = sum(vec_a[k] * vec_b[k] for k in common)
    norm_a = math.sqrt(sum(v * v for v in vec_a.values()))
    norm_b = math.sqrt(sum(v * v for v in vec_b.values()))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot / (norm_a * norm_b)


def tfidf_cosine(text_a: str, text_b: str) -> float:
    """Cosine similarity of TF-IDF vectors, in [0, 1]. Uses jieba when available."""
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    vectors = _build_tfidf([tokens_a, tokens_b])
    return _cosine_similarity(vectors[0], vectors[1])


_LLM_SCORE_PROMPT = """You are a strict skill-deduplication judge. Decide how similar two procedural skills are.
Return ONLY a JSON object: {{"score": <0.0-1.0>, "similar": <true/false>, "reason": "<brief>"}}
Score 1.0 = same workflow and should be merged; 0.0 = unrelated.

## Skill A
name: {name_a}
description: {desc_a}
triggers: {triggers_a}
content:
{body_a}

## Skill B
name: {name_b}
description: {desc_b}
triggers: {triggers_b}
content:
{body_b}
"""


def _llm_similarity_score(
    new_skill: dict[str, Any], other: dict[str, Any], llm_fn: LLMFn
) -> Optional[float]:
    def _trunc(s: str, n: int) -> str:
        s = s or ""
        return s if len(s) <= n else s[:n] + "\n..."

    body_a = _trunc(str(new_skill.get("content", new_skill.get("body", ""))), 2400)
    body_b = _trunc(str(other.get("content", other.get("body", ""))), 2400)
    prompt = _LLM_SCORE_PROMPT.format(
        name_a=new_skill.get("name", ""),
        desc_a=new_skill.get("description", ""),
        triggers_a=", ".join(new_skill.get("triggers") or []),
        body_a=body_a,
        name_b=other.get("name", ""),
        desc_b=other.get("description", ""),
        triggers_b=", ".join(other.get("triggers") or []),
        body_b=body_b,
    )
    # Audit R2-14: split the previous monolithic try/except. LLM provider
    # errors (network / timeout / 401) are a soft "unavailable" — caller
    # records the event and falls back to the deterministic layer. A
    # provider-up-but-response-garbled condition is a hard "corrupt" signal
    # that must surface (raise) so callers don't silently degrade dedup.
    try:
        response = llm_fn(prompt).strip()
    except Exception as e:
        logger.warning("LLM similarity unavailable: %s", e)
        raise SimilarityLLMUnavailable(str(e)) from e
    m = re.search(r"\{[^{}]*\}", response, re.DOTALL)
    if not m:
        m = re.search(r"\{.*\}", response, re.DOTALL)
    if not m:
        raise SimilarityResponseCorrupt(
            f"LLM dedup response has no JSON object: {response[:120]!r}"
        )
    try:
        data = json.loads(m.group())
        score = float(data.get("score", 0.0))
    except (json.JSONDecodeError, ValueError, TypeError) as e:
        raise SimilarityResponseCorrupt(
            f"LLM dedup response JSON unparseable: {e}"
        ) from e
    if data.get("similar") is False and score >= 0.99:
        score = min(score, 0.5)
    return max(0.0, min(1.0, score))


class SkillSimilarity:
    """Three-pass funnel: trigger Jaccard → TF-IDF cosine → optional LLM."""

    # Internal gates: pass TF-IDF only when Jaccard is weak (avoids redundant work).
    _JACCARD_STRONG = 0.3
    _TFIDF_GATE = 0.5

    def __init__(
        self,
        llm_fn: Optional[LLMFn] = None,
        *,
        jaccard_strong: float = 0.3,
        tfidf_gate: float = 0.5,
    ) -> None:
        self._llm_fn = llm_fn
        self._jaccard_strong = jaccard_strong
        self._tfidf_gate = tfidf_gate

    def set_llm_fn(self, fn: Optional[LLMFn]) -> None:
        self._llm_fn = fn

    def find_similar(
        self,
        new_skill: dict[str, Any],
        existing_skills: list[dict[str, Any]],
        threshold: float = 0.6,
    ) -> list[tuple[dict[str, Any], float]]:
        """Return (skill, score) pairs with final score >= threshold."""
        if not existing_skills:
            return []

        new_name = new_skill.get("name")
        new_triggers = list(new_skill.get("triggers") or [])
        new_text = _skill_text(new_skill)

        results: list[tuple[dict[str, Any], float]] = []

        for skill in existing_skills:
            if skill.get("name") == new_name:
                continue

            j = trigger_jaccard(new_triggers, list(skill.get("triggers") or []))

            if j >= self._jaccard_strong:
                medium_score: float = j
            else:
                t = tfidf_cosine(new_text, _skill_text(skill))
                if t >= self._tfidf_gate:
                    medium_score = t
                else:
                    continue

            final_score = self._resolve_final_score(new_skill, skill, medium_score)

            if final_score >= threshold:
                results.append((skill, final_score))

        results.sort(key=lambda x: -x[1])
        return results

    def _resolve_final_score(
        self,
        new_skill: dict[str, Any],
        skill: dict[str, Any],
        medium_score: float,
    ) -> float:
        """Pick final dedup score: LLM tier if available, else medium_score.

        Audit R2-14: the LLM tier's failure modes (unreachable / corrupt) are
        recorded to the dedup-status buffer so /诊断 can detect dedup drift.
        Corrupt responses also log at ERROR with full traceback — the
        deterministic layer is a fallback, not a silent downgrade.
        """
        if self._llm_fn is None:
            return medium_score
        try:
            return _llm_similarity_score(new_skill, skill, self._llm_fn)
        except SimilarityResponseCorrupt as exc:
            logger.error(
                "LLM dedup response corrupt; falling back to medium score: %s",
                exc,
                exc_info=exc,
            )
            _record_dedup_status("corrupt", str(exc))
            return medium_score
        except SimilarityLLMUnavailable as exc:
            _record_dedup_status("unavailable", str(exc))
            return medium_score
