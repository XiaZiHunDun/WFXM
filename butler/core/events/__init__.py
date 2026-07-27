"""Event sourcing infrastructure for session state management.

Provides domain event classes, event store implementations,
event replay for state reconstruction, and event bus for pub/sub.

Includes session lifecycle events:
- SessionStarted, SessionEnded
- ToolCalled, ToolCompleted, ToolFailedEvent
- ApprovalRequested, ApprovalGranted, ApprovalDenied
- SessionState and SessionStateProjector for state reconstruction
"""

from __future__ import annotations

from .event_store import (
    DomainEvent,
    EnhancedEventBus,
    EventBatch,
    EventBus,
    EventDefinition,
    EventRegistry,
    EventSourcingHandler,
    EventStore,
    InMemoryEventStore,
    Projector,
    Scope,
    generate_event_id,
    get_event_definition,
    get_global_event_bus,
    get_global_event_registry,
    get_global_event_store,
    now_utc,
    register_event,
    reset_global_event_bus,
    reset_global_event_store,
)
from .session_events import (
    ApprovalDenied,
    ApprovalGranted,
    ApprovalRequested,
    ERROR_OCCURRED,
    MESSAGE_RECEIVED,
    MESSAGE_SENT,
    SESSION_ENDED,
    SESSION_STARTED,
    SessionEnded,
    SessionStarted,
    SessionState,
    SessionStateProjector,
    TOOL_CALLED,
    TOOL_COMPLETED,
    TOOL_FAILED,
    ToolCalled,
    ToolCompleted,
    ToolFailedEvent,
    create_session_started,
    create_tool_called,
    create_tool_completed,
    create_tool_failed,
    register_session_events,
)

__all__ = [
    # Core
    "DomainEvent",
    "EnhancedEventBus",
    "EventBatch",
    "EventBus",
    "EventDefinition",
    "EventRegistry",
    "EventSourcingHandler",
    "EventStore",
    "InMemoryEventStore",
    "Projector",
    "Scope",
    "generate_event_id",
    "get_event_definition",
    "get_global_event_bus",
    "get_global_event_registry",
    "get_global_event_store",
    "now_utc",
    "register_event",
    "reset_global_event_bus",
    "reset_global_event_store",
    # Event Classes
    "ApprovalDenied",
    "ApprovalGranted",
    "ApprovalRequested",
    "SessionEnded",
    "SessionStarted",
    "SessionState",
    "SessionStateProjector",
    "ToolCalled",
    "ToolCompleted",
    "ToolFailedEvent",
    # Event Definitions
    "ERROR_OCCURRED",
    "MESSAGE_RECEIVED",
    "MESSAGE_SENT",
    "SESSION_ENDED",
    "SESSION_STARTED",
    "TOOL_CALLED",
    "TOOL_COMPLETED",
    "TOOL_FAILED",
    # Factory Functions
    "create_session_started",
    "create_tool_called",
    "create_tool_completed",
    "create_tool_failed",
    "register_session_events",
]
