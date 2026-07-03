"""Delegate yield task-id resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def resolve_recent_delegate_task_id_safe() -> str | None:
    def _run() -> str:
        from butler.execution_context import get_current_session_key
        from butler.runtime.task_store import list_recent_tasks

        sk = str(get_current_session_key() or "").strip()
        recent = list_recent_tasks(sk, limit=1)
        if not recent:
            raise ValueError("no recent delegate task")
        tid = str(recent[0].get("task_id") or "").strip()
        if not tid:
            raise ValueError("empty task_id")
        return tid

    result = safe_best_effort(
        _run,
        label="delegate_yield.recent_task_id",
        default=None,
    )
    return result if isinstance(result, str) else None
