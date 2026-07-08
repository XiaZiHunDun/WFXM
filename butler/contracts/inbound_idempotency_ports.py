"""Port for resetting gateway inbound idempotency from L5 session boundary."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class InboundIdempotencyPort(Protocol):
    def reset_session(self, session_id: str) -> None: ...


__all__ = ["InboundIdempotencyPort"]
