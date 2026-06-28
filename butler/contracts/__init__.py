"""Cross-layer Protocol contracts (ENG-6 / P1-D).

* ``butler.contracts.events.EventsSink`` — transcript / tool-audit surface
* ``butler.core.events_sink.EventsSink`` — compaction hooks + urgent inbound

Gateway's :class:`butler.gateway.events_sink_impl.GatewayEventsSink` implements
both; ``register_gateway_events_sink()`` wires the contracts registry to the
same live instance installed for core compaction.
"""

from butler.contracts.events import EventsSink
from butler.contracts.sink_registry import get_events_sink, set_events_sink

__all__ = [
    "EventsSink",
    "get_events_sink",
    "set_events_sink",
]
