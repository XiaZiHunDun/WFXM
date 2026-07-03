"""In-process ring buffer for recent thread_item outbound events."""

from __future__ import annotations

import threading
from typing import Any

from butler.gateway.outbound_events import OutboundEvent

_LOCK = threading.Lock()
_MAX = 32
_recent: list[dict[str, Any]] = []


def record_thread_item(event: OutboundEvent | dict[str, Any]) -> None:
    from butler.gateway.item_event_sink_ops import serialize_thread_item_event_safe

    payload = serialize_thread_item_event_safe(event)
    if payload is None:
        return
    with _LOCK:
        _recent.append(payload)
        if len(_recent) > _MAX:
            del _recent[: len(_recent) - _MAX]


def recent_thread_items(limit: int = 16) -> list[dict[str, Any]]:
    with _LOCK:
        return list(_recent[-max(1, int(limit)) :])
