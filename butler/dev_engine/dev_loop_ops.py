"""Dev loop best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.dev_engine.dev_state import DevPhase


def effective_dev_max_fix_rounds_safe(*, env_default: int) -> int:
    def _run() -> int:
        from butler.ops.eval_config_overrides import effective_dev_max_fix_rounds

        return int(effective_dev_max_fix_rounds(env_default))

    result = safe_best_effort(
        _run,
        label="dev_loop.max_fix_rounds",
        default=env_default,
    )
    return int(result)


def on_task_start_safe(task_id: str, task_description: str) -> None:
    def _run() -> None:
        from butler.dev_engine.dev_metrics import get_collector

        get_collector().on_task_start(task_id, task_description)

    safe_best_effort(_run, label="dev_loop.task_start", default=None)


def maybe_promote_to_review_safe(new_phase: DevPhase) -> DevPhase:
    def _run() -> DevPhase:
        from butler.dev_engine.dev_tools import auto_review_enabled

        if auto_review_enabled() and new_phase == DevPhase.DONE:
            return DevPhase.REVIEW
        return new_phase

    result = safe_best_effort(_run, label="dev_loop.auto_review", default=new_phase)
    return result if isinstance(result, DevPhase) else new_phase


def emit_transition_metrics_safe(
    state: Any,
    *,
    from_phase: str,
    event: str,
    to_phase: str,
) -> None:
    def _run() -> None:
        from butler.dev_engine.dev_metrics import get_collector

        task_id = getattr(state, "_metrics_task_id", "")
        if task_id:
            get_collector().on_transition(task_id, from_phase, event, to_phase)

    safe_best_effort(_run, label="dev_loop.transition_metrics", default=None)
