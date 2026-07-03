"""Doom loop session key fail-closed helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def current_doom_loop_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    result = safe_best_effort(
        _run,
        label="doom_loop.session_key",
        default="",
    )
    return str(result or "").strip()
