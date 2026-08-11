"""Event sourcing infrastructure for session state management.

Provides:
- Domain event base classes with metadata
- Event store protocol and memory implementation
- Event replay for state reconstruction
- Event bus for pub/sub pattern
- Event definition registry with versioning support
- Saga pattern for distributed transactions
- Replay optimization with snapshots and time-travel

This is a shim file for backward compatibility.
The actual implementation is split into:
- event_types.py: DomainEvent, EventDefinition, EventRegistry and utilities
- event_store_protocol.py: EventStore protocol and InMemoryEventStore
- event_bus.py: EventBus and EnhancedEventBus
- event_handlers.py: EventSourcingHandler, Projector, EventBatch, Scope
- saga.py: SagaStep, SagaOrchestrator for distributed transactions
- replay.py: ReplayOptimizer, EventTimeTravel, Snapshot
"""

from __future__ import annotations

from butler.core.effects import Result, Ok, Err
from butler.core.events.event_types import (
    DomainEvent,
    EventDefinition,
    EventRegistry,
    generate_event_id,
    now_utc,
    get_global_event_registry,
    register_event,
    get_event_definition,
)
from butler.core.events.event_store_protocol import (
    EventStore,
    InMemoryEventStore,
    get_global_event_store,
    reset_global_event_store,
)
from butler.core.events.event_bus import (
    EventBus,
    EnhancedEventBus,
    get_global_event_bus,
    reset_global_event_bus,
)
from butler.core.events.event_handlers import (
    EventSourcingHandler,
    Projector,
    EventBatch,
    Scope,
)
from butler.core.events.saga import (
    SagaContext,
    SagaOrchestrator,
    SagaStep,
    build_saga,
    create_step,
)
from butler.core.events.replay import (
    EventQueryOptimizer,
    EventTimeTravel,
    ReplayOptimizer,
    ReplayStrategy,
    Snapshot,
)


__all__ = [
    "DomainEvent",
    "EventStore",
    "InMemoryEventStore",
    "EventSourcingHandler",
    "EventBus",
    "EnhancedEventBus",
    "EventDefinition",
    "EventRegistry",
    "EventBatch",
    "Projector",
    "Scope",
    "generate_event_id",
    "now_utc",
    "get_global_event_store",
    "get_global_event_bus",
    "get_global_event_registry",
    "reset_global_event_store",
    "reset_global_event_bus",
    "register_event",
    "get_event_definition",
    "Result",
    "Ok",
    "Err",
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
