"""Session todos tool context best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def current_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(
        _run,
        label="session_todos_tools.session_key",
        default="default",
    )
    text = str(result or "").strip()
    return text or "default"
