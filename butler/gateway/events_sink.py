"""Gateway wiring for :class:`butler.contracts.events.EventsSink` (ENG-6 续)."""

from __future__ import annotations

from butler.gateway.events_sink_impl import GatewayEventsSink, install_gateway_events_sink


def register_gateway_events_sink() -> GatewayEventsSink:
    """Wire the live ``GatewayEventsSink`` into the contracts registry (idempotent)."""
    return install_gateway_events_sink()


__all__ = ["GatewayEventsSink", "register_gateway_events_sink"]
