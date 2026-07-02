"""Best-effort memory tool context helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def tool_session_key_default() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return get_current_session_key() or ""

    return safe_best_effort(
        _run,
        label="memory_tools.session_key",
        default="",
    ) or ""
