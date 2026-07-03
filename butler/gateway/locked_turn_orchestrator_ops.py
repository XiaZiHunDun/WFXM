"""Locked turn in-context phase failure helpers (P0-A)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def run_in_context_phases_or_fail(
    handler: Any,
    state: Any,
    *,
    welcome_prefix: str,
    session_key: str,
) -> tuple[str | None, str | None]:
    """Return ``(result, error_response)``; ``error_response`` set on failure."""
    from butler.gateway.locked_phase_registry import run_in_context_phases
    from butler.gateway.locked_phases import _phase_format_error_card
    from butler.gateway.user_errors import format_gateway_user_error

    try:
        response = run_in_context_phases(
            handler,
            state,
            welcome_prefix=welcome_prefix,
        )
        if response is not None:
            return response, None
        return str(getattr(state, "out", "") or ""), None
    except Exception as exc:
        state.health["error"] = str(exc)
        handler._session_registry.set_health(session_key, state.health)
        elapsed = time.monotonic() - float(getattr(state, "turn_started", 0.0) or 0.0)
        logger.error(
            "Message handling failed session=%s elapsed=%.1fs: %s",
            session_key,
            elapsed,
            exc,
            exc_info=True,
        )
        card = _phase_format_error_card(exc, elapsed)
        return None, card or format_gateway_user_error(exc)
