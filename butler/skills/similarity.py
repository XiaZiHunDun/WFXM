"""Skill similarity — three-layer funnel for detecting similar skills.

Layer 1: Trigger set Jaccard overlap (cheap, no LLM)
Layer 2: TF-IDF cosine similarity (moderate, no LLM)
Layer 3: LLM semantic judgment (precise, only for candidates)
"""
from __future__ import annotations

import json
import logging
import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Callable, Coroutine, Optional

logger = logging.getLogger(__name__)

LLMCallFn = Callable[[str], Coroutine[Any, Any, str]]

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


@dataclass
class SimilarityJudgment:
    similar: bool
    confidence: float
    reason: str
    merge_suggestion: str


@dataclass
class SimilarityResult:
    skill_name: str
    pre_score: float
    pre_method: str
    judgment: Optional[SimilarityJudgment] = None


_STOP_WORDS = frozenset([
    "的", "了", "和", "是", "在", "有", "不", "这", "就", "都",
    "也", "人", "我", "他", "她", "你", "们", "对", "个", "被",
    "到", "可以", "或", "等", "但", "如果", "那",
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "and", "or", "but", "not", "this", "that", "it", "as",
])


def trigger_jaccard(triggers_a: list[str], triggers_b: list[str]) -> float:
    if not triggers_a or not triggers_b:
        return 0.0
    set_a = {t.strip().lower() for t in triggers_a}
    set_b = {t.strip().lower() for t in triggers_b}
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def _tokenize(text: str) -> list[str]:
    jb = _ensure_jieba()
    if jb is not None:
        tokens = list(jb.cut(text))
    else:
        tokens = re.findall(r'[\u4e00-\u9fff]+|[a-zA-Z]+', text.lower())
    return [t.strip().lower() for t in tokens
            if t.strip() and len(t.strip()) > 1 and t.strip().lower() not in _STOP_WORDS]


def _build_tfidf(docs: list[list[str]]) -> list[dict[str, float]]:
    n_docs = len(docs)
    if n_docs == 0:
        return []
    df: Counter = Counter()
    for doc in docs:
        for t in set(doc):
            df[t] += 1
    vectors = []
    for doc in docs:
        tf: Counter = Counter(doc)
        total = len(doc) if doc else 1
        vec = {}
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
    tokens_a = _tokenize(text_a)
    tokens_b = _tokenize(text_b)
    if not tokens_a or not tokens_b:
        return 0.0
    vectors = _build_tfidf([tokens_a, tokens_b])
    return _cosine_similarity(vectors[0], vectors[1])


_LLM_JUDGE_PROMPT = """你是一个 Skill 相似度判定专家。请判断以下两个 Skill 是否本质上描述同一类工作流程，应该被合并为一个。

## Skill A
名称: {name_a}
描述: {desc_a}
触发词: {triggers_a}
内容:
{body_a}

## Skill B
名称: {name_b}
描述: {desc_b}
触发词: {triggers_b}
内容:
{body_b}

## 判断标准
- 如果两个 Skill 的核心目标和操作流程高度重叠（只是措辞或角度不同），则应合并
- 如果两个 Skill 虽有部分重叠但各自有独特且不可替代的流程，则不应合并

请严格按以下 JSON 格式输出：
{{"similar": true/false, "confidence": 0.0-1.0, "reason": "简短解释", "merge_suggestion": "如果合并，新 skill 应叫什么名字"}}"""


async def llm_judge(skill_a: dict, skill_b: dict, llm_call: LLMCallFn) -> SimilarityJudgment:
    prompt = _LLM_JUDGE_PROMPT.format(
        name_a=skill_a.get("name", ""), desc_a=skill_a.get("description", ""),
        triggers_a=", ".join(skill_a.get("triggers", [])),
        body_a=(skill_a.get("body", ""))[:2000],
        name_b=skill_b.get("name", ""), desc_b=skill_b.get("description", ""),
        triggers_b=", ".join(skill_b.get("triggers", [])),
        body_b=(skill_b.get("body", ""))[:2000],
    )
    try:
        response = await llm_call(prompt)
        json_match = re.search(r'\{[^{}]*\}', response.strip(), re.DOTALL)
        if json_match:
            data = json.loads(json_match.group())
            return SimilarityJudgment(
                similar=bool(data.get("similar", False)),
                confidence=float(data.get("confidence", 0.0)),
                reason=str(data.get("reason", "")),
                merge_suggestion=str(data.get("merge_suggestion", "")),
            )
    except Exception as e:
        logger.error("LLM judge error: %s", e)
    return SimilarityJudgment(similar=False, confidence=0.0, reason="LLM judgment failed", merge_suggestion="")


class SkillSimilarity:
    """Three-layer funnel for detecting similar skills."""

    def __init__(self, trigger_threshold: float = 0.3, tfidf_threshold: float = 0.5,
                 llm_threshold: float = 0.7, llm_call: Optional[LLMCallFn] = None):
        self.trigger_threshold = trigger_threshold
        self.tfidf_threshold = tfidf_threshold
        self.llm_threshold = llm_threshold
        self._llm_call = llm_call

    def set_llm_call(self, fn: LLMCallFn) -> None:
        self._llm_call = fn

    async def find_similar(self, new_skill: dict, existing_skills: list[dict]) -> list[SimilarityResult]:
        if not existing_skills:
            return []
        candidates: list[tuple[dict, float, str]] = []
        new_triggers = new_skill.get("triggers", [])
        new_text = f"{new_skill.get('description', '')} {new_skill.get('body', '')}"
        for skill in existing_skills:
            if skill.get("name") == new_skill.get("name"):
                continue
            jaccard = trigger_jaccard(new_triggers, skill.get("triggers", []))
            if jaccard >= self.trigger_threshold:
                candidates.append((skill, jaccard, "trigger_jaccard"))
                continue
            skill_text = f"{skill.get('description', '')} {skill.get('body', '')}"
            cos_sim = tfidf_cosine(new_text, skill_text)
            if cos_sim >= self.tfidf_threshold:
                candidates.append((skill, cos_sim, "tfidf_cosine"))
        if not candidates:
            return []
        if not self._llm_call:
            return [SimilarityResult(skill_name=s.get("name", ""), pre_score=score, pre_method=method)
                    for s, score, method in candidates]
        confirmed = []
        for skill, pre_score, method in candidates:
            judgment = await llm_judge(new_skill, skill, self._llm_call)
            if judgment.similar and judgment.confidence >= self.llm_threshold:
                confirmed.append(SimilarityResult(
                    skill_name=skill.get("name", ""), pre_score=pre_score,
                    pre_method=method, judgment=judgment))
        return confirmed
