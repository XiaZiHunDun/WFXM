"""Layering seam for gateway side-effects (R1-3 fix).

Core modules call the convenience shims below instead of importing gateway.
The unified :class:`EventsSink` Protocol and registry live in
``butler.contracts``; this module re-exports them and forwards shims to the
single contracts registry.
"""

from __future__ import annotations

import logging
from typing import Any, cast

from butler.contracts.events import EventsSink, NullEventsSink, UrgentInbound
from butler.contracts.sink_registry import get_events_sink, set_events_sink

logger = logging.getLogger(__name__)


def invoke_hook(name: str, **kwargs: Any) -> list[Any]:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        hooked = get_events_sink().invoke_hook(name, **kwargs)
        return cast(list[Any], hooked)
    except Exception as exc:  # noqa: BLE001 — best-effort, never break the caller
        logger.debug("events_sink.invoke_hook skipped: %s", exc)
        return []


def emit_context_compaction(
    *,
    phase: str,
    thread_id: str = "",
    tokens_before: int = 0,
    tokens_after: int = 0,
    messages_before: int = 0,
    messages_after: int = 0,
    source: str = "context",
    remote: bool = False,
) -> None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        get_events_sink().emit_context_compaction(
            phase=phase,
            thread_id=thread_id,
            tokens_before=tokens_before,
            tokens_after=tokens_after,
            messages_before=messages_before,
            messages_after=messages_after,
            source=source,
            remote=remote,
        )
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("events_sink.emit_context_compaction skipped: %s", exc)


def pop_urgent_inbound(session_key: str) -> UrgentInbound | None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        return get_events_sink().pop_urgent_inbound(session_key)
    except Exception as exc:  # noqa: BLE001 — best-effort
        logger.debug("events_sink.pop_urgent_inbound skipped: %s", exc)
        return None


__all__ = [
    "EventsSink",
    "NullEventsSink",
    "UrgentInbound",
    "emit_context_compaction",
    "get_events_sink",
    "invoke_hook",
    "pop_urgent_inbound",
    "set_events_sink",
]
