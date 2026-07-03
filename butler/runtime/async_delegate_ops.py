"""Async delegate scheduling best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def mark_delegate_task_background_safe(task_id: str) -> None:
    def _run() -> None:
        from butler.runtime.task_store import update_task

        update_task(task_id, background=True)

    safe_best_effort(_run, label="async_delegate.mark_background", default=None)
