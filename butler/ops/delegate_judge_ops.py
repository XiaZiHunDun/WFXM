"""Delegate judge LangFuse push best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def push_delegate_judge_score_safe(judge: Any, *, trace_id: str) -> bool:
    def _run() -> bool:
        from butler.ops.eval_bridge import EvalScore, push_score

        return bool(
            push_score(
                EvalScore(
                    name="delegate_judge.quality",
                    value=judge.score,
                    comment=judge.comment,
                    category="delegate_judge",
                    trace_id=trace_id,
                    metadata=judge.to_dict(),
                )
            )
        )

    result = safe_best_effort(
        _run,
        label="delegate_judge.push_score",
        default=False,
    )
    return bool(result)
