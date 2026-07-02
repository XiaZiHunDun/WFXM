"""Layering seam for gateway side-effects (R1-3 fix).

Core modules call the convenience shims below instead of importing gateway.
The unified :class:`EventsSink` Protocol and registry live in
``butler.contracts``; this module re-exports them and forwards shims to the
single contracts registry.
"""

from __future__ import annotations

from typing import Any

from butler.contracts.events import EventsSink, NullEventsSink, UrgentInbound
from butler.contracts.sink_registry import get_events_sink, set_events_sink


def invoke_hook(name: str, **kwargs: Any) -> list[Any]:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    from butler.core.events_sink_ops import invoke_hook_safe

    return invoke_hook_safe(name, **kwargs)


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
    from butler.core.events_sink_ops import emit_context_compaction_safe

    emit_context_compaction_safe(
        phase=phase,
        thread_id=thread_id,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        messages_before=messages_before,
        messages_after=messages_after,
        source=source,
        remote=remote,
    )


def pop_urgent_inbound(session_key: str) -> UrgentInbound | None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    from butler.core.events_sink_ops import pop_urgent_inbound_safe

    return pop_urgent_inbound_safe(session_key)


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
