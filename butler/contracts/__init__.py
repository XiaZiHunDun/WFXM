"""Cross-layer Protocol contracts (ENG-6 / P1-D).

Two complementary sink protocols (do not merge — different lifecycles):

* :class:`EventsSink` — transcript / tool-audit (this module)
* ``butler.core.events_sink.EventsSink`` — compaction hooks + urgent inbound

Gateway :class:`butler.gateway.events_sink_impl.GatewayEventsSink` implements
**both**; ``register_gateway_events_sink()`` wires the contracts registry to
the live core instance.
"""

from butler.contracts.events import EventsSink
from butler.contracts.sink_registry import get_events_sink, set_events_sink

__all__ = [
    "EventsSink",
    "get_events_sink",
    "set_events_sink",
]
