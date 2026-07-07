"""B9 lessons experience follow-up best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any, cast

from butler.core.best_effort import safe_best_effort
from butler.dev_engine.b9_types import B9Result, B9TaskSpec


def follow_up_lesson_experience_safe(
    row: dict[str, Any],
    result: B9Result,
    spec: B9TaskSpec,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.ops.b9_lessons import follow_up_lesson_experience

        return cast(dict[str, Any], follow_up_lesson_experience(row, result, spec))

    fallback = {"action": "skipped", "detail": "error"}
    out = safe_best_effort(
        _run,
        label="b9_lessons.experience_followup",
        default=fallback,
    )
    return out if isinstance(out, dict) else fallback
