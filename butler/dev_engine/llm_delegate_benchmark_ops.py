"""LLM delegate benchmark best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.core.best_effort import safe_best_effort


def guard_live_delegate_void(
    fn: Callable[[], None],
    *,
    tools_used: list[str],
    errors: list[str],
) -> tuple[bool, list[str], list[str]] | None:
    try:
        fn()
        return None
    except Exception as exc:
        errors.append(str(exc))
        return False, tools_used, errors


def guard_b9_task_run(fn: Callable[[], None], result: Any) -> None:
    try:
        fn()
    except Exception as exc:
        result.failure_reasons.append(str(exc))


def record_b9_run_lesson_safe(result: Any, spec: Any) -> None:
    def _run() -> None:
        from butler.ops.b9_lessons import record_b9_run_lesson

        record_b9_run_lesson(result, spec)

    safe_best_effort(_run, label="llm_delegate_benchmark.record_lesson", default=None)
