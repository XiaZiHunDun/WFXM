"""Bridge between approval flow and domain event system.

Emits domain events when approval states change:
- ApprovalRequested: When a permission approval is pending
- ApprovalGranted: When an approval is granted (once or always)
- ApprovalDenied: When an approval is denied or revoked
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from butler.core.events.event_types import DomainEvent, generate_event_id
from butler.core.events.event_store import get_global_event_bus
from butler.core.events.session_events import (
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
)

logger = logging.getLogger(__name__)


def emit_approval_requested_event(
    session_id: str,
    tool_name: str,
    reason: str = "",
    permission_type: str = "rule",
    fingerprint: str = "",
) -> None:
    """Emit an ApprovalRequested event to the event bus."""
    try:
        args_preview = ""
        if fingerprint:
            args_preview = json.dumps(
                {"fingerprint": fingerprint, "tool": tool_name},
                ensure_ascii=False,
            )[:200]

        event = ApprovalRequested(
            event_id=generate_event_id(),
            event_type="APPROVAL_REQUESTED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data={
                "tool_name": tool_name,
                "reason": reason,
                "permission_type": permission_type,
                "fingerprint": fingerprint,
            },
            session_id=session_id,
            tool_name=tool_name,
            reason=reason,
            permission_type=permission_type,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted ApprovalRequested event: tool=%s, fp=%s",
            tool_name,
            fingerprint[:8] if fingerprint else "N/A",
        )
    except Exception as exc:
        logger.debug("Failed to emit ApprovalRequested event: %s", exc)


def emit_approval_granted_event(
    session_id: str,
    tool_name: str,
    granted_by: str = "owner",
    duration_type: str = "once",
    permission: str = "",
    pattern: str = "",
) -> None:
    """Emit an ApprovalGranted event to the event bus."""
    try:
        event = ApprovalGranted(
            event_id=generate_event_id(),
            event_type="APPROVAL_GRANTED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data={
                "tool_name": tool_name,
                "granted_by": granted_by,
                "duration_type": duration_type,
                "permission": permission,
                "pattern": pattern,
            },
            session_id=session_id,
            tool_name=tool_name,
            granted_by=granted_by,
            duration_type=duration_type,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted ApprovalGranted event: tool=%s, type=%s",
            tool_name,
            duration_type,
        )
    except Exception as exc:
        logger.debug("Failed to emit ApprovalGranted event: %s", exc)


def emit_approval_denied_event(
    session_id: str,
    tool_name: str,
    denied_by: str = "owner",
    reason: str = "",
) -> None:
    """Emit an ApprovalDenied event to the event bus."""
    try:
        event = ApprovalDenied(
            event_id=generate_event_id(),
            event_type="APPROVAL_DENIED.1",
            session_key=session_id,
            timestamp=datetime.now(timezone.utc),
            data={
                "tool_name": tool_name,
                "denied_by": denied_by,
                "reason": reason,
            },
            session_id=session_id,
            tool_name=tool_name,
            denied_by=denied_by,
            reason=reason,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted ApprovalDenied event: tool=%s, reason=%s",
            tool_name,
            reason[:50] if reason else "N/A",
        )
    except Exception as exc:
        logger.debug("Failed to emit ApprovalDenied event: %s", exc)


def emit_approval_revoked_event(
    session_id: str,
    tool_name: str = "",
    permission: str = "",
    revoked_by: str = "owner",
) -> None:
    """Emit an ApprovalDenied event for revocation."""
    emit_approval_denied_event(
        session_id=session_id,
        tool_name=tool_name,
        denied_by=revoked_by,
        reason=f"Revoked: permission={permission or '*'}",
    )


__all__ = [
    "emit_approval_requested_event",
    "emit_approval_granted_event",
    "emit_approval_denied_event",
    "emit_approval_revoked_event",
]
