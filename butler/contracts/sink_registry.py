"""Runtime registration for :class:`EventsSink` (gateway wires at startup)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.events import EventsSink

_LOCK = threading.RLock()
_SINK: EventsSink | None = None


def set_events_sink(sink: EventsSink | None) -> None:
    global _SINK
    with _LOCK:
        _SINK = sink


def get_events_sink() -> EventsSink | None:
    with _LOCK:
        return _SINK


__all__ = ["get_events_sink", "set_events_sink"]
