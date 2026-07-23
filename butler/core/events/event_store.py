"""Event sourcing infrastructure for session state management.

Provides:
- Domain event base classes with metadata
- Event store protocol and memory implementation
- Event replay for state reconstruction
- Event bus for pub/sub pattern
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Generic, Iterable, Protocol, TypeVar

from butler.core.effects import Result, Ok, Err, collect_results

T = TypeVar("T")


@dataclass(frozen=True)
class DomainEvent:
    """Base class for all domain events.

    Attributes:
        event_id: Unique identifier for the event
        event_type: Type of the event
        session_key: Session identifier
        timestamp: When the event occurred (UTC)
        data: Event payload
        version: Event schema version
        metadata: Additional context
    """

    event_id: str
    event_type: str
    session_key: str
    timestamp: datetime
    data: dict[str, Any]
    version: int = 1
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert event to dict for storage/serialization."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "session_key": self.session_key,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
            "version": self.version,
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Result["DomainEvent", Exception]:
        """Create event from dict."""
        try:
            return Ok(
                cls(
                    event_id=data["event_id"],
                    event_type=data["event_type"],
                    session_key=data["session_key"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    data=data.get("data", {}),
                    version=data.get("version", 1),
                    metadata=data.get("metadata", {}),
                )
            )
        except Exception as e:
            return Err(e)

    def __lt__(self, other: "DomainEvent") -> bool:
        """Compare by timestamp for ordering."""
        return self.timestamp < other.timestamp


def generate_event_id() -> str:
    """Generate a unique event ID."""
    import uuid

    return str(uuid.uuid4())


def now_utc() -> datetime:
    """Return current UTC datetime."""
    return datetime.utcnow()


class EventStore(Protocol):
    """Protocol for event storage operations."""

    def append(self, event: DomainEvent) -> Result[None, Exception]:
        """Append an event to the store."""
        ...

    def append_batch(self, events: Iterable[DomainEvent]) -> Result[None, Exception]:
        """Append multiple events atomically."""
        ...

    def get_events_for_session(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Get all events for a session, ordered by timestamp."""
        ...

    def get_events_by_type(
        self, session_key: str, event_type: str
    ) -> Result[list[DomainEvent], Exception]:
        """Get events of a specific type for a session."""
        ...

    def get_event(self, event_id: str) -> Result[DomainEvent | None, Exception]:
        """Get a single event by ID."""
        ...

    def replay(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Replay all events for a session in order."""
        ...

    def clear_session(self, session_key: str) -> Result[None, Exception]:
        """Remove all events for a session."""
        ...


class InMemoryEventStore:
    """In-memory event store implementation.

    Thread-safe storage for domain events.
    Suitable for testing and single-process deployments.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events_by_session: dict[str, list[DomainEvent]] = {}
        self._events_by_id: dict[str, DomainEvent] = {}

    def append(self, event: DomainEvent) -> Result[None, Exception]:
        """Append an event to the store."""
        try:
            with self._lock:
                if event.session_key not in self._events_by_session:
                    self._events_by_session[event.session_key] = []
                self._events_by_session[event.session_key].append(event)
                self._events_by_id[event.event_id] = event
            return Ok(None)
        except Exception as e:
            return Err(e)

    def append_batch(self, events: Iterable[DomainEvent]) -> Result[None, Exception]:
        """Append multiple events atomically."""
        try:
            with self._lock:
                for event in events:
                    if event.session_key not in self._events_by_session:
                        self._events_by_session[event.session_key] = []
                    self._events_by_session[event.session_key].append(event)
                    self._events_by_id[event.event_id] = event
            return Ok(None)
        except Exception as e:
            return Err(e)

    def get_events_for_session(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Get all events for a session, ordered by timestamp."""
        try:
            with self._lock:
                events = self._events_by_session.get(session_key, [])
                sorted_events = sorted(events, key=lambda e: e.timestamp)
            return Ok(sorted_events)
        except Exception as e:
            return Err(e)

    def get_events_by_type(
        self, session_key: str, event_type: str
    ) -> Result[list[DomainEvent], Exception]:
        """Get events of a specific type for a session."""
        try:
            result = self.get_events_for_session(session_key)
            if result.is_err():
                return result
            filtered = [e for e in result.unwrap() if e.event_type == event_type]
            return Ok(filtered)
        except Exception as e:
            return Err(e)

    def get_event(self, event_id: str) -> Result[DomainEvent | None, Exception]:
        """Get a single event by ID."""
        try:
            with self._lock:
                return Ok(self._events_by_id.get(event_id))
        except Exception as e:
            return Err(e)

    def replay(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Replay all events for a session in order."""
        return self.get_events_for_session(session_key)

    def clear_session(self, session_key: str) -> Result[None, Exception]:
        """Remove all events for a session."""
        try:
            with self._lock:
                if session_key in self._events_by_session:
                    # Remove from events_by_id
                    for event in self._events_by_session[session_key]:
                        self._events_by_id.pop(event.event_id, None)
                    # Remove from events_by_session
                    del self._events_by_session[session_key]
            return Ok(None)
        except Exception as e:
            return Err(e)

    def get_all_sessions(self) -> Result[list[str], Exception]:
        """Get all session keys with events."""
        try:
            with self._lock:
                return Ok(list(self._events_by_session.keys()))
        except Exception as e:
            return Err(e)

    def count_events(self) -> Result[int, Exception]:
        """Count all events in the store."""
        try:
            with self._lock:
                return Ok(sum(len(events) for events in self._events_by_session.values()))
        except Exception as e:
            return Err(e)


class EventSourcingHandler(Generic[T]):
    """Event sourcing handler for state reconstruction.

    Uses event replay to rebuild aggregate state from historical events.

    Example:
        def apply_event(state, event):
            match event.event_type:
                case "SESSION_START":
                    return SessionState(...)
                case "TOOL_ACTION":
                    return state.with_tool_action(...)
                case _:
                    return state

        handler = EventSourcingHandler(initial_state, apply_event)
        state = handler.replay(events)
    """

    def __init__(
        self,
        initial_state: T,
        apply_event: Callable[[T, DomainEvent], T],
    ) -> None:
        self._initial_state = initial_state
        self._apply_event = apply_event

    def replay(self, events: Iterable[DomainEvent]) -> T:
        """Replay events to reconstruct state."""
        state = self._initial_state
        for event in sorted(events, key=lambda e: e.timestamp):
            state = self._apply_event(state, event)
        return state

    def replay_from_store(self, store: EventStore, session_key: str) -> Result[T, Exception]:
        """Replay events from a store for a session."""
        result = store.get_events_for_session(session_key)
        if result.is_err():
            return result
        return Ok(self.replay(result.unwrap()))


class EventBus:
    """Simple event bus for pub/sub pattern.

    Allows components to subscribe to event types and react to events.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._subscribers: dict[str, list[Callable[[DomainEvent], Any]]] = {}

    def subscribe(
        self, event_type: str, handler: Callable[[DomainEvent], Any]
    ) -> Callable[[], None]:
        """Subscribe to an event type.

        Returns an unsubscribe function.
        """
        with self._lock:
            if event_type not in self._subscribers:
                self._subscribers[event_type] = []
            self._subscribers[event_type].append(handler)

        def unsubscribe() -> None:
            with self._lock:
                if event_type in self._subscribers:
                    self._subscribers[event_type].remove(handler)

        return unsubscribe

    def publish(self, event: DomainEvent) -> Result[list[Any], Exception]:
        """Publish an event to all subscribers."""
        try:
            with self._lock:
                handlers = self._subscribers.get(event.event_type, [])

            results = [handler(event) for handler in handlers]
            return Ok(results)
        except Exception as e:
            return Err(e)

    def publish_many(self, events: Iterable[DomainEvent]) -> Result[list[list[Any]], Exception]:
        """Publish multiple events."""
        return collect_results([self.publish(event) for event in events])


# Global singleton instances (for testing and simple use cases)
_global_event_store: InMemoryEventStore | None = None
_global_event_bus: EventBus | None = None


def get_global_event_store() -> InMemoryEventStore:
    """Get or create the global event store."""
    global _global_event_store
    if _global_event_store is None:
        _global_event_store = InMemoryEventStore()
    return _global_event_store


def get_global_event_bus() -> EventBus:
    """Get or create the global event bus."""
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus


def reset_global_event_store() -> None:
    """Reset the global event store (for testing)."""
    global _global_event_store
    _global_event_store = InMemoryEventStore()


def reset_global_event_bus() -> None:
    """Reset the global event bus (for testing)."""
    global _global_event_bus
    _global_event_bus = EventBus()


__all__ = [
    "DomainEvent",
    "EventStore",
    "InMemoryEventStore",
    "EventSourcingHandler",
    "EventBus",
    "generate_event_id",
    "now_utc",
    "get_global_event_store",
    "get_global_event_bus",
    "reset_global_event_store",
    "reset_global_event_bus",
]
