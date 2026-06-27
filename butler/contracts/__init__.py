"""Cross-layer Protocol contracts (ENG-6 / P1-D)."""

from butler.contracts.events import EventsSink
from butler.contracts.sink_registry import get_events_sink, set_events_sink

__all__ = [
    "EventsSink",
    "get_events_sink",
    "set_events_sink",
]
