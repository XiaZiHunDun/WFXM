"""Best-effort session interrupt helpers for gateway handler (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from collections.abc import Callable

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger("butler.gateway.message_handler")


def interrupt_delegates_safe(session_key: str) -> None:
    def _run() -> None:
        from butler.runtime.delegate_registry import interrupt_delegates_for_session

        n = interrupt_delegates_for_session(session_key)
        if n:
            logger.info(
                "Gateway interrupted %d delegate loop(s) session=%s",
                n,
                session_key,
            )

    safe_best_effort(_run, label="message_handler.interrupt_delegates", default=None)


def interrupt_agent_loop_safe(loop: Any, *, session_key: str) -> None:
    if loop is None or not hasattr(loop, "interrupt"):
        return

    def _run() -> None:
        loop.interrupt()
        logger.info("Gateway interrupt requested session=%s", session_key)

    safe_best_effort(_run, label="message_handler.interrupt_loop", default=None)


def interrupt_session_loop_safe(
    sessions: dict[str, Any],
    session_key: str,
) -> None:
    interrupt_delegates_safe(session_key)
    interrupt_agent_loop_safe(sessions.get(session_key), session_key=session_key)


def run_prequeue_interrupt_safe(
    interrupt_fn: Callable[[], None],
    *,
    log_debug: Callable[[str], None],
) -> None:
    try:
        interrupt_fn()
    except Exception as exc:
        log_debug(f"Prequeue interrupt failed: {exc}")
