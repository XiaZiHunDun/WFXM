"""Event sourcing infrastructure for session state management.

Provides domain event classes, event store implementations,
event replay for state reconstruction, and event bus for pub/sub.
"""

from __future__ import annotations

from .event_store import (
    DomainEvent,
    EventBus,
    EventSourcingHandler,
    EventStore,
    InMemoryEventStore,
    generate_event_id,
    get_global_event_bus,
    get_global_event_store,
    now_utc,
    reset_global_event_bus,
    reset_global_event_store,
)

__all__ = [
    "DomainEvent",
    "EventBus",
    "EventSourcingHandler",
    "EventStore",
    "InMemoryEventStore",
    "generate_event_id",
    "get_global_event_bus",
    "get_global_event_store",
    "now_utc",
    "reset_global_event_bus",
    "reset_global_event_store",
]
