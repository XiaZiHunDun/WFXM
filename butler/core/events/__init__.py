"""Event sourcing infrastructure for session state management.

Provides domain event classes, event store implementations,
event replay for state reconstruction, and event bus for pub/sub.

Includes session lifecycle events:
- SessionStarted, SessionEnded
- ToolCalled, ToolCompleted, ToolFailedEvent
- ApprovalRequested, ApprovalGranted, ApprovalDenied
- SessionState and SessionStateProjector for state reconstruction

Storage implementations:
- InMemoryEventStore: For testing and single-process use
- FileEventStore: Persistent JSONL-based storage
- HybridEventStore: Memory cache + file persistence

Maintenance:
- EventRetentionPolicy: Configuration for event cleanup
- EventArchiver: Archive old events to compressed storage
- EventCleanupService: Automated cleanup based on retention policy

Query optimization:
- EventIndex: Lightweight in-memory index for fast lookups
- EventQuery: High-level query API with filtering and aggregation
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
from .file_event_store import FileEventStore
from .hybrid_event_store import HybridEventStore
from .event_cleanup import (
    EventRetentionPolicy,
    EventArchiver,
    EventCleanupService,
)
from .event_query import (
    EventIndexEntry,
    EventIndex,
    EventQueryFilter,
    EventQuery,
)
from .approval_event_emitter import (
    emit_approval_denied_event,
    emit_approval_granted_event,
    emit_approval_requested_event,
    emit_approval_revoked_event,
)
from .message_event_emitter import (
    emit_error_occurred_event,
    emit_message_received_event,
    emit_message_sent_event,
)
from .saga import (
    SagaContext,
    SagaOrchestrator,
    SagaStep,
    build_saga,
    create_step,
)
from .replay import (
    EventQueryOptimizer,
    EventTimeTravel,
    ReplayOptimizer,
    ReplayStrategy,
    Snapshot,
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
    "FileEventStore",
    "HybridEventStore",
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
    # Maintenance
    "EventRetentionPolicy",
    "EventArchiver",
    "EventCleanupService",
    # Query
    "EventIndexEntry",
    "EventIndex",
    "EventQueryFilter",
    "EventQuery",
    # Approval Event Emitters
    "emit_approval_requested_event",
    "emit_approval_granted_event",
    "emit_approval_denied_event",
    "emit_approval_revoked_event",
    # Message Event Emitters
    "emit_message_received_event",
    "emit_message_sent_event",
    "emit_error_occurred_event",
    # Saga
    "SagaContext",
    "SagaOrchestrator",
    "SagaStep",
    "build_saga",
    "create_step",
    # Replay Optimization
    "Snapshot",
    "ReplayStrategy",
    "ReplayOptimizer",
    "EventTimeTravel",
    "EventQueryOptimizer",
]
