"""Runtime registration for InboundIdempotencyPort."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.inbound_idempotency_ports import InboundIdempotencyPort

_LOCK = threading.RLock()
_PORT: InboundIdempotencyPort | None = None


def set_inbound_idempotency_port(port: InboundIdempotencyPort | None) -> None:
    global _PORT
    with _LOCK:
        _PORT = port


def get_inbound_idempotency_port() -> InboundIdempotencyPort | None:
    with _LOCK:
        return _PORT


__all__ = ["get_inbound_idempotency_port", "set_inbound_idempotency_port"]
