"""Gateway wiring for :class:`butler.contracts.events.EventsSink` (ENG-6 续).

The compaction / hooks sink lives in ``butler.core.events_sink`` and is
installed by ``events_sink_impl`` on import. This module registers the **same**
``GatewayEventsSink`` instance with ``butler.contracts.sink_registry`` so
transcript-oriented callers can use the contracts Protocol without importing
gateway from core.
"""

from __future__ import annotations

from butler.gateway.events_sink_impl import GatewayEventsSink


def register_gateway_events_sink() -> GatewayEventsSink:
    """Wire contracts registry to the live ``GatewayEventsSink`` (idempotent)."""
    from butler.contracts.sink_registry import set_events_sink as set_contracts_sink
    from butler.core.events_sink import get_events_sink

    sink = get_events_sink()
    if not isinstance(sink, GatewayEventsSink):
        from butler.gateway.events_sink_impl import install_gateway_events_sink

        sink = install_gateway_events_sink()
    set_contracts_sink(sink)
    return sink


__all__ = ["GatewayEventsSink", "register_gateway_events_sink"]
