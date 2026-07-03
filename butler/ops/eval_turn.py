"""Per-turn runtime scoring and LangFuse push (O4)."""

from __future__ import annotations

import re
from typing import Any

from butler.ops.eval_bridge import EvalReport, push_scores
from butler.ops.eval_scoring import MultiDimScore, ScoreResult, score_response_quality
from butler.ops.tool_routing import score_delegate_routing, score_runtime_tool_routing

_WORD_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}", re.UNICODE)


def _meaningful_keywords(text: str, *, limit: int = 8) -> list[str]:
    words = _WORD_RE.findall(text or "")
    seen: set[str] = set()
    out: list[str] = []
    for w in words:
        key = w.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(w)
        if len(out) >= limit:
            break
    return out


def score_runtime_intent(user_text: str, response_text: str) -> ScoreResult:
    """Heuristic intent score without golden labels."""
    if not (response_text or "").strip():
        return ScoreResult(
            dimension="intent_accuracy",
            score=0.0,
            comment="empty response",
        )
    keywords = _meaningful_keywords(user_text)
    if not keywords:
        return ScoreResult(
            dimension="intent_accuracy",
            score=0.7,
            comment="no keywords; response present",
        )
    text_lower = response_text.lower()
    hits = sum(1 for kw in keywords if kw.lower() in text_lower)
    score = hits / len(keywords)
    if score < 0.3 and len(response_text.strip()) > 40:
        score = 0.3
    return ScoreResult(
        dimension="intent_accuracy",
        score=score,
        details={"keyword_hits": hits, "keyword_total": len(keywords)},
        comment=f"runtime keyword overlap {hits}/{len(keywords)}",
    )


def score_runtime_turn(
    *,
    user_text: str,
    response_text: str,
    tools_used: list[str] | None = None,
    session_id: str = "",
    include_memory: bool = True,
) -> MultiDimScore:
    """Score a production turn without dataset labels."""
    result = MultiDimScore()
    result.scores.append(score_runtime_intent(user_text, response_text))
    result.scores.append(score_runtime_tool_routing(user_text, tools_used))
    result.scores.append(score_delegate_routing(user_text, tools_used))
    result.scores.append(score_response_quality(response_text=response_text))

    if include_memory and session_id:
        from butler.ops.eval_turn_ops import score_memory_effectiveness_for_session_safe

        memory_score = score_memory_effectiveness_for_session_safe(session_id)
        if memory_score is not None:
            result.scores.append(memory_score)

    return result


def push_turn_scores(
    *,
    user_text: str,
    response_text: str,
    tools_used: list[str] | None = None,
    session_id: str = "",
    trace_id: str = "",
) -> tuple[MultiDimScore, EvalReport]:
    """Score a turn and push dimension scores to LangFuse."""
    multi = score_runtime_turn(
        user_text=user_text,
        response_text=response_text,
        tools_used=tools_used,
        session_id=session_id,
        include_memory=True,
    )
    scores = multi.to_eval_scores(trace_id=trace_id)
    # LangFuse dashboard uses short names from eval_feedback thresholds
    alias_map = {
        "eval.intent_accuracy": "intent_accuracy",
        "eval.tool_selection": "tool_selection",
        "eval.delegate_routing": "delegate_routing",
        "eval.response_quality": "response_quality",
        "eval.memory_effectiveness": "memory_effectiveness",
    }
    for s in scores:
        if s.name in alias_map:
            s.name = alias_map[s.name]
    report = push_scores(scores)
    return multi, report


def extract_tools_used(diagnostics: dict[str, Any] | None) -> list[str]:
    if not diagnostics:
        return []
    raw = diagnostics.get("tools_used")
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    return []


__all__ = [
    "extract_tools_used",
    "push_turn_scores",
    "score_runtime_intent",
    "score_runtime_turn",
]
