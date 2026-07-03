"""Todo continuation goal-loop probe best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def is_goal_loop_active_safe(session_key: str) -> bool:
    def _run() -> bool:
        from butler.core.goal_loop import is_goal_loop_active

        return bool(is_goal_loop_active(session_key))

    result = safe_best_effort(
        _run,
        label="todo_continuation.goal_loop_active",
        default=False,
    )
    return bool(result)
