"""B9 production weekly probe best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.dev_engine.b9_types import B9Result, B9TaskSpec


def summarize_prod_experience_effectiveness_safe() -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.ops.prod_experience_effectiveness import (
            summarize_prod_experience_effectiveness,
        )

        return cast(dict[str, Any], summarize_prod_experience_effectiveness())

    result = safe_best_effort(
        _run,
        label="b9_prod_weekly.experience_effectiveness",
        default={},
    )
    return result if isinstance(result, dict) else {}


def record_b9_run_lesson_safe(result: B9Result, spec: B9TaskSpec) -> None:
    def _run() -> None:
        from butler.ops.b9_lessons import record_b9_run_lesson

        record_b9_run_lesson(result, spec)

    safe_best_effort(_run, label="b9_prod_weekly.record_lesson", default=None)
