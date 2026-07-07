"""Best-effort helpers for gateway locked turn phases (P0-A / P2-F)."""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional, cast

logger = logging.getLogger(__name__)


def run_hygiene_compress(state: Any, compress_fn: Callable[[], None]) -> None:
    from butler.core.best_effort import safe_best_effort

    def _run() -> None:
        try:
            compress_fn()
        except Exception as exc:
            state.health["hygiene_error"] = str(exc)
            logger.warning("Gateway hygiene compression skipped: %s", exc)
            raise

    safe_best_effort(_run, label="locked_phases.hygiene_compress", default=None)


def format_gateway_error_card(exc: BaseException, turn_elapsed: float) -> Optional[str]:
    """Build structured error card; returns None when renderer fails (fail-loud)."""
    try:
        from butler.gateway.error_cards import format_error_card

        exc_type = type(exc).__name__
        if "timeout" in exc_type.lower() or "Timeout" in exc_type:
            card = format_error_card(
                "delegate_timeout",
                role="agent",
                elapsed=round(turn_elapsed),
            )
            return str(card) if isinstance(card, str) else None
        if "Permission" in exc_type:
            card = format_error_card(
                "permission_deny",
                tool="message_handler",
                reason=str(exc)[:200],
            )
            return str(card) if isinstance(card, str) else None
        card = format_error_card(
            "tool_error",
            tool="message_handler",
            error=str(exc),
        )
        return str(card) if isinstance(card, str) else None
    except Exception:
        logger.error("error card formatting failed", exc_info=True)
        return None


__all__ = [
    "format_gateway_error_card",
    "run_hygiene_compress",
]
