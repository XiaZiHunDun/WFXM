"""App-server style Thread/Turn/Item outbound events (Codex protocol subset)."""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from butler.gateway.outbound_events import OutboundEvent
import logging

logger = logging.getLogger(__name__)

SCHEMA = "butler.app-server/1"


@dataclass(frozen=True)
class ThreadItemSpec:
    thread_id: str = ""
    turn_id: str = ""
    item_id: str = ""
    item_type: str = ""
    phase: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": SCHEMA,
            "thread_id": self.thread_id,
            "turn_id": self.turn_id,
            "item_id": self.item_id,
            "item_type": self.item_type,
            "phase": self.phase,
            "payload": dict(self.payload),
        }


def _new_item_id(prefix: str = "item") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def thread_item_event(
    item_type: str,
    *,
    phase: str,
    thread_id: str = "",
    turn_id: str = "",
    item_id: str = "",
    payload: dict[str, Any] | None = None,
) -> OutboundEvent:
    spec = ThreadItemSpec(
        thread_id=str(thread_id or "").strip(),
        turn_id=str(turn_id or "").strip(),
        item_id=item_id or _new_item_id(item_type[:8] or "item"),
        item_type=str(item_type or "").strip(),
        phase=str(phase or "").strip(),
        payload=dict(payload or {}),
    )
    return OutboundEvent(
        kind="thread_item",
        phase=spec.phase,
        name=spec.item_type,
        detail=(spec.payload.get("detail") or "")[:200],
        extra=spec.to_dict(),
        monotonic=time.monotonic(),
    )


def context_compaction_item(
    *,
    phase: str,
    thread_id: str = "",
    turn_id: str = "",
    item_id: str = "",
    tokens_before: int = 0,
    tokens_after: int = 0,
    messages_before: int = 0,
    messages_after: int = 0,
    source: str = "context",
    remote: bool = False,
) -> OutboundEvent:
    return thread_item_event(
        "context_compaction",
        phase=phase,
        thread_id=thread_id,
        turn_id=turn_id,
        item_id=item_id,
        payload={
            "source": source[:32],
            "tokens_before": max(0, int(tokens_before)),
            "tokens_after": max(0, int(tokens_after)),
            "messages_before": max(0, int(messages_before)),
            "messages_after": max(0, int(messages_after)),
            "remote": bool(remote),
        },
    )


def emit_thread_item(event: OutboundEvent) -> None:
    """Best-effort push to global item sink (health / diagnostics)."""
    try:
        from butler.gateway.item_event_sink import record_thread_item

        record_thread_item(event)
    except Exception as exc:
        logger.debug("emit thread item skipped: %s", exc)
