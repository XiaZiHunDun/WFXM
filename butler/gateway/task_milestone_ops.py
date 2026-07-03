"""Task milestone best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def delegate_progress_notify_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.gateway.completion_notify import delegate_progress_notify_enabled

        return bool(delegate_progress_notify_enabled())

    result = safe_best_effort(
        _run,
        label="task_milestone.delegate_progress_notify",
        default=False,
    )
    return bool(result)
