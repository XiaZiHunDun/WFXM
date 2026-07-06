"""Lightweight delegate outcome judge → LangFuse score (phase 3).

Heuristic judge (default). Optional LLM rubric when
``BUTLER_EVAL_DELEGATE_JUDGE=llm`` and transport is configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, cast


@dataclass
class DelegateJudgeResult:
    score: float
    comment: str
    dimensions: dict[str, float]
    mode: str = "heuristic"

    def to_dict(self) -> dict[str, Any]:
        return {
            "score": self.score,
            "comment": self.comment,
            "dimensions": self.dimensions,
            "mode": self.mode,
        }


def judge_mode() -> str:
    raw = os.getenv("BUTLER_EVAL_DELEGATE_JUDGE", "heuristic").strip().lower()
    return raw if raw in ("heuristic", "llm", "off") else "heuristic"


def judge_delegate_outcome(
    *,
    success: bool,
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
    task: str = "",
    summary: str = "",
) -> DelegateJudgeResult | None:
    """Score a delegate completion for LangFuse ranking."""
    if judge_mode() == "off":
        return None

    issues = issues or []
    dev_engine = dev_engine or {}
    verify_passed = dev_engine.get("verify_passed")
    edits = int(dev_engine.get("edits") or 0)
    fixes = int(dev_engine.get("fixes") or 0)

    intent = 1.0 if success else 0.2
    if summary.strip():
        intent = min(1.0, intent + 0.1)
    if task and summary and any(w in summary.lower() for w in task.lower().split()[:4]):
        intent = min(1.0, intent + 0.1)

    constraints = 1.0
    if issues:
        constraints = max(0.0, 1.0 - min(0.6, 0.15 * len(issues)))

    tests = 1.0
    if verify_passed is False:
        tests = 0.2
    elif verify_passed is True:
        tests = 1.0
    elif success and edits == 0:
        tests = 0.4

    rescue = 1.0
    if fixes > 2:
        rescue = 0.7
    if not success and edits > 0:
        rescue = 0.5

    overall = round((intent * 0.35 + constraints * 0.25 + tests * 0.3 + rescue * 0.1), 3)
    comment_parts = []
    if not success:
        comment_parts.append("delegate_failed")
    if verify_passed is False:
        comment_parts.append("verify_failed")
    if issues:
        comment_parts.append(issues[0][:120])
    comment = "; ".join(comment_parts) or ("passed" if success else "failed")

    return DelegateJudgeResult(
        score=overall,
        comment=comment,
        dimensions={
            "intent_completion": round(intent, 3),
            "constraint_safety": round(constraints, 3),
            "test_adequacy": round(tests, 3),
            "rescue_efficiency": round(rescue, 3),
        },
        mode="heuristic",
    )


def push_delegate_judge_score(
    judge: DelegateJudgeResult,
    *,
    trace_id: str = "",
) -> bool:
    if not trace_id:
        return False
    from butler.ops.delegate_judge_ops import push_delegate_judge_score_safe

    return cast(bool, push_delegate_judge_score_safe(judge, trace_id=trace_id))


def maybe_judge_and_push(
    *,
    success: bool,
    issues: list[str] | None = None,
    dev_engine: dict[str, Any] | None = None,
    task: str = "",
    summary: str = "",
    trace_id: str = "",
) -> DelegateJudgeResult | None:
    judge = judge_delegate_outcome(
        success=success,
        issues=issues,
        dev_engine=dev_engine,
        task=task,
        summary=summary,
    )
    if judge is not None and trace_id:
        push_delegate_judge_score(judge, trace_id=trace_id)
    return judge


__all__ = [
    "DelegateJudgeResult",
    "judge_delegate_outcome",
    "judge_mode",
    "maybe_judge_and_push",
    "push_delegate_judge_score",
]
