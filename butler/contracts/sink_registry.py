"""Runtime registration for :class:`EventsSink` (gateway wires at startup)."""

from __future__ import annotations

import threading

from butler.contracts.events import EventsSink, NullEventsSink

_LOCK = threading.RLock()
_SINK: EventsSink = NullEventsSink()


def set_events_sink(sink: EventsSink | None) -> None:
    global _SINK
    with _LOCK:
        _SINK = sink if sink is not None else NullEventsSink()


def get_events_sink() -> EventsSink:
    """Return the active sink (never ``None``; defaults to :class:`NullEventsSink`)."""
    with _LOCK:
        return _SINK


__all__ = ["get_events_sink", "set_events_sink"]
