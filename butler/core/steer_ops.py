"""Steer session-key resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def resolve_session_key_from_context_safe() -> str | None:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        sk = str(get_current_session_key() or "").strip()
        if not sk:
            raise ValueError("no session key in context")
        return sk

    result = safe_best_effort(_run, label="steer.session_key", default=None)
    text = str(result or "").strip()
    return text or None
