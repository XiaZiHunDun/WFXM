"""Session todos best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def resolve_session_key_safe(session_key: str = "") -> str:
    key = str(session_key or "").strip()
    if key:
        return key

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(
        _run,
        label="session_todos.session_key",
        default="default",
    )
    return str(result or "default")


def record_todo_updated_safe(session_key: str, *, count: int) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_todo_updated

        record_todo_updated(session_key, count=count)

    safe_best_effort(_run, label="session_todos.record_updated", default=None)
