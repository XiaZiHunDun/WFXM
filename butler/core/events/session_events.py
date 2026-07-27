"""Session lifecycle event definitions for event sourcing.

Defines standard event types for session state management,
enabling event-driven session tracking and state reconstruction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from butler.core.events.event_types import (
    DomainEvent,
    EventDefinition,
    register_event,
)

# --- Session Lifecycle Events ---

SESSION_STARTED = EventDefinition(
    type="SESSION_STARTED",
    version=1,
    aggregate_field="session_id",
)

SESSION_ENDED = EventDefinition(
    type="SESSION_ENDED",
    version=1,
    aggregate_field="session_id",
)

MESSAGE_RECEIVED = EventDefinition(
    type="MESSAGE_RECEIVED",
    version=1,
    aggregate_field="session_id",
)

MESSAGE_SENT = EventDefinition(
    type="MESSAGE_SENT",
    version=1,
    aggregate_field="session_id",
)

TOOL_CALLED = EventDefinition(
    type="TOOL_CALLED",
    version=1,
    aggregate_field="session_id",
)

TOOL_COMPLETED = EventDefinition(
    type="TOOL_COMPLETED",
    version=1,
    aggregate_field="session_id",
)

TOOL_FAILED = EventDefinition(
    type="TOOL_FAILED",
    version=1,
    aggregate_field="session_id",
)

APPROVAL_REQUESTED = EventDefinition(
    type="APPROVAL_REQUESTED",
    version=1,
    aggregate_field="session_id",
)

APPROVAL_GRANTED = EventDefinition(
    type="APPROVAL_GRANTED",
    version=1,
    aggregate_field="session_id",
)

APPROVAL_DENIED = EventDefinition(
    type="APPROVAL_DENIED",
    version=1,
    aggregate_field="session_id",
)

ERROR_OCCURRED = EventDefinition(
    type="ERROR_OCCURRED",
    version=1,
    aggregate_field="session_id",
)


# --- Session Event Classes ---

@dataclass(frozen=True)
class SessionStarted(DomainEvent):
    """Session lifecycle: session started."""
    session_id: str = ""
    project_path: str = ""
    tenant: str = "default"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "SESSION_STARTED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class SessionEnded(DomainEvent):
    """Session lifecycle: session ended."""
    session_id: str = ""
    reason: str = "user_disconnected"
    duration_ms: int = 0
    turn_count: int = 0

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "SESSION_ENDED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class ToolCalled(DomainEvent):
    """Tool execution: tool was called."""
    session_id: str = ""
    tool_name: str = ""
    args_preview: str = ""
    call_id: str = ""
    turn_number: int = 0

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "TOOL_CALLED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class ToolCompleted(DomainEvent):
    """Tool execution: tool completed successfully."""
    session_id: str = ""
    tool_name: str = ""
    call_id: str = ""
    result_preview: str = ""
    duration_ms: int = 0
    success: bool = True

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "TOOL_COMPLETED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class ToolFailedEvent(DomainEvent):
    """Tool execution: tool failed."""
    session_id: str = ""
    tool_name: str = ""
    call_id: str = ""
    error_message: str = ""
    error_kind: str = "retry"
    duration_ms: int = 0

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "TOOL_FAILED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class ApprovalRequested(DomainEvent):
    """Permission: approval was requested."""
    session_id: str = ""
    tool_name: str = ""
    reason: str = ""
    permission_type: str = "rule"

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "APPROVAL_REQUESTED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class ApprovalGranted(DomainEvent):
    """Permission: approval was granted."""
    session_id: str = ""
    tool_name: str = ""
    granted_by: str = "owner"
    duration_type: str = "once"  # once or always

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "APPROVAL_GRANTED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


@dataclass(frozen=True)
class ApprovalDenied(DomainEvent):
    """Permission: approval was denied."""
    session_id: str = ""
    tool_name: str = ""
    denied_by: str = "owner"
    reason: str = ""

    def __post_init__(self) -> None:
        if not self.event_type:
            object.__setattr__(self, 'event_type', "APPROVAL_DENIED.1")

    @property
    def aggregate_id(self) -> str:
        return self.session_id


# --- Session State ---

@dataclass
class SessionState:
    """Reconstructable session state derived from event sourcing.

    This state is rebuilt by replaying session events, enabling
    state reconstruction and audit trails.
    """
    session_id: str = ""
    status: str = "active"  # active, ended
    turn_count: int = 0
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    granted_approvals: list[dict[str, Any]] = field(default_factory=list)
    denials: list[dict[str, Any]] = field(default_factory=list)
    errors: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_active(self) -> bool:
        return self.status == "active"

    @property
    def has_pending_approval(self) -> bool:
        return len(self.pending_approvals) > 0

    @property
    def recent_errors(self) -> list[dict[str, Any]]:
        return self.errors[-5:]


# --- Session State Projector ---

class SessionStateProjector:
    """Projects session events into SessionState.

    Implements the projector pattern for event-sourced state
    reconstruction. Given a sequence of events, produces the
    current session state.
    """

    def __init__(self) -> None:
        self._state: Optional[SessionState] = None

    def initialize(self, session_id: str) -> None:
        """Initialize projector for a new session."""
        self._state = SessionState(session_id=session_id)

    @property
    def state(self) -> Optional[SessionState]:
        return self._state

    def apply_event(self, event: DomainEvent) -> None:
        """Apply a single event to reconstruct state."""
        if self._state is None:
            return

        if isinstance(event, SessionStarted):
            self._state.session_id = event.session_id
            self._state.metadata["project_path"] = event.project_path
            self._state.metadata["tenant"] = event.tenant

        elif isinstance(event, SessionEnded):
            self._state.status = "ended"
            self._state.metadata["end_reason"] = event.reason
            self._state.metadata["duration_ms"] = event.duration_ms
            self._state.turn_count = event.turn_count

        elif isinstance(event, ToolCalled):
            self._state.turn_count = max(self._state.turn_count, event.turn_number)
            self._state.tool_calls.append({
                "tool_name": event.tool_name,
                "call_id": event.call_id,
                "turn": event.turn_number,
                "status": "called",
            })

        elif isinstance(event, ToolCompleted):
            for call in reversed(self._state.tool_calls):
                if call.get("call_id") == event.call_id:
                    call["status"] = "completed"
                    call["duration_ms"] = event.duration_ms
                    call["success"] = event.success
                    break

        elif isinstance(event, ToolFailedEvent):
            for call in reversed(self._state.tool_calls):
                if call.get("call_id") == event.call_id:
                    call["status"] = "failed"
                    call["error"] = event.error_message
                    call["error_kind"] = event.error_kind
                    break
            self._state.errors.append({
                "tool_name": event.tool_name,
                "error": event.error_message,
                "kind": event.error_kind,
            })

        elif isinstance(event, ApprovalRequested):
            self._state.pending_approvals.append({
                "tool_name": event.tool_name,
                "reason": event.reason,
                "permission_type": event.permission_type,
            })

        elif isinstance(event, ApprovalGranted):
            self._state.granted_approvals.append({
                "tool_name": event.tool_name,
                "granted_by": event.granted_by,
                "duration_type": event.duration_type,
            })
            self._state.pending_approvals = [
                a for a in self._state.pending_approvals
                if a.get("tool_name") != event.tool_name
            ]

        elif isinstance(event, ApprovalDenied):
            self._state.denials.append({
                "tool_name": event.tool_name,
                "denied_by": event.denied_by,
                "reason": event.reason,
            })
            self._state.pending_approvals = [
                a for a in self._state.pending_approvals
                if a.get("tool_name") != event.tool_name
            ]

    def replay_events(self, events: list[DomainEvent], session_id: str) -> SessionState:
        """Replay a full event stream to reconstruct state."""
        self.initialize(session_id)
        for event in events:
            self.apply_event(event)
        return self._state


# --- Event Factory Helpers ---

def create_session_started(
    session_id: str,
    project_path: str = "",
    tenant: str = "default",
    **metadata: Any,
) -> SessionStarted:
    """Create a SessionStarted event."""
    from datetime import datetime, timezone
    from butler.core.events.event_types import generate_event_id

    return SessionStarted(
        event_id=generate_event_id(),
        event_type="SESSION_STARTED.1",
        session_key=session_id,
        timestamp=datetime.now(timezone.utc),
        data={"project_path": project_path, "tenant": tenant},
        session_id=session_id,
        project_path=project_path,
        tenant=tenant,
        metadata=metadata,
    )


def create_tool_called(
    session_id: str,
    tool_name: str,
    call_id: str,
    turn_number: int = 0,
    args_preview: str = "",
) -> ToolCalled:
    """Create a ToolCalled event."""
    from datetime import datetime, timezone
    from butler.core.events.event_types import generate_event_id

    return ToolCalled(
        event_id=generate_event_id(),
        event_type="TOOL_CALLED.1",
        session_key=session_id,
        timestamp=datetime.now(timezone.utc),
        data={"tool_name": tool_name, "call_id": call_id},
        session_id=session_id,
        tool_name=tool_name,
        call_id=call_id,
        turn_number=turn_number,
        args_preview=args_preview,
    )


def create_tool_completed(
    session_id: str,
    tool_name: str,
    call_id: str,
    success: bool = True,
    duration_ms: int = 0,
    result_preview: str = "",
) -> ToolCompleted:
    """Create a ToolCompleted event."""
    from datetime import datetime, timezone
    from butler.core.events.event_types import generate_event_id

    return ToolCompleted(
        event_id=generate_event_id(),
        event_type="TOOL_COMPLETED.1",
        session_key=session_id,
        timestamp=datetime.now(timezone.utc),
        data={"tool_name": tool_name, "success": success},
        session_id=session_id,
        tool_name=tool_name,
        call_id=call_id,
        success=success,
        duration_ms=duration_ms,
        result_preview=result_preview,
    )


def create_tool_failed(
    session_id: str,
    tool_name: str,
    call_id: str,
    error_message: str,
    error_kind: str = "retry",
    duration_ms: int = 0,
) -> ToolFailedEvent:
    """Create a ToolFailedEvent."""
    from datetime import datetime, timezone
    from butler.core.events.event_types import generate_event_id

    return ToolFailedEvent(
        event_id=generate_event_id(),
        event_type="TOOL_FAILED.1",
        session_key=session_id,
        timestamp=datetime.now(timezone.utc),
        data={"tool_name": tool_name, "error": error_message},
        session_id=session_id,
        tool_name=tool_name,
        call_id=call_id,
        error_message=error_message,
        error_kind=error_kind,
        duration_ms=duration_ms,
    )


def register_session_events() -> None:
    """Register all session event definitions globally."""
    definitions = [
        SESSION_STARTED,
        SESSION_ENDED,
        MESSAGE_RECEIVED,
        MESSAGE_SENT,
        TOOL_CALLED,
        TOOL_COMPLETED,
        TOOL_FAILED,
        APPROVAL_REQUESTED,
        APPROVAL_GRANTED,
        APPROVAL_DENIED,
        ERROR_OCCURRED,
    ]
    for defn in definitions:
        register_event(defn)


# Auto-register on import
register_session_events()


__all__ = [
    # Event Classes
    "SessionStarted",
    "SessionEnded",
    "ToolCalled",
    "ToolCompleted",
    "ToolFailedEvent",
    "ApprovalRequested",
    "ApprovalGranted",
    "ApprovalDenied",
    # State
    "SessionState",
    "SessionStateProjector",
    # Event Definitions
    "SESSION_STARTED",
    "SESSION_ENDED",
    "MESSAGE_RECEIVED",
    "MESSAGE_SENT",
    "TOOL_CALLED",
    "TOOL_COMPLETED",
    "TOOL_FAILED",
    "APPROVAL_REQUESTED",
    "APPROVAL_GRANTED",
    "APPROVAL_DENIED",
    "ERROR_OCCURRED",
    # Factory Functions
    "create_session_started",
    "create_tool_called",
    "create_tool_completed",
    "create_tool_failed",
    "register_session_events",
]
