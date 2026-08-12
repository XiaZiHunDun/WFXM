"""Bridge between message handling and domain event system.

Emits domain events when messages are processed:
- MessageReceived: When an inbound message is received
- MessageSent: When a response message is sent
- ErrorOccurred: When an error occurs during processing
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from butler.core.events.event_types import DomainEvent, generate_event_id
from butler.core.events.event_store import get_global_event_bus

logger = logging.getLogger(__name__)


def emit_message_received_event(
    session_id: str,
    content_preview: str = "",
    message_type: str = "text",
    channel: str = "gateway",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a MessageReceived event to the event bus."""
    try:
        data_payload: dict[str, Any] = {
            "content_preview": content_preview[:200],
            "message_type": message_type,
            "channel": channel,
        }
        if metadata:
            data_payload["metadata"] = metadata

        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="MESSAGE_RECEIVED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data=data_payload,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted MessageReceived event: channel=%s, type=%s",
            channel,
            message_type,
        )
    except Exception as exc:
        logger.debug("Failed to emit MessageReceived event: %s", exc)


def emit_message_sent_event(
    session_id: str,
    content_preview: str = "",
    message_type: str = "text",
    channel: str = "gateway",
    duration_ms: int = 0,
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit a MessageSent event to the event bus."""
    try:
        data_payload: dict[str, Any] = {
            "content_preview": content_preview[:200],
            "message_type": message_type,
            "channel": channel,
            "duration_ms": duration_ms,
        }
        if metadata:
            data_payload["metadata"] = metadata

        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="MESSAGE_SENT.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data=data_payload,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted MessageSent event: channel=%s, type=%s, duration=%dms",
            channel,
            message_type,
            duration_ms,
        )
    except Exception as exc:
        logger.debug("Failed to emit MessageSent event: %s", exc)


def emit_error_occurred_event(
    session_id: str,
    error_type: str,
    error_message: str,
    source: str = "unknown",
    metadata: dict[str, Any] | None = None,
) -> None:
    """Emit an ErrorOccurred event to the event bus."""
    try:
        data_payload: dict[str, Any] = {
            "error_type": error_type,
            "error_message": error_message[:500],
            "source": source,
        }
        if metadata:
            data_payload["metadata"] = metadata

        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ERROR_OCCURRED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data=data_payload,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted ErrorOccurred event: type=%s, source=%s",
            error_type,
            source,
        )
    except Exception as exc:
        logger.debug("Failed to emit ErrorOccurred event: %s", exc)


__all__ = [
    "emit_message_received_event",
    "emit_message_sent_event",
    "emit_error_occurred_event",
]
