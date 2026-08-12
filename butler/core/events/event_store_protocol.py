"""Event store protocol and in-memory implementation.

Provides:
- EventStore protocol defining storage operations
- InMemoryEventStore for testing and single-process deployments
- Global event store utilities
"""

from __future__ import annotations

import threading
from typing import Iterable, Protocol

from butler.core.effects import Result, Ok, Err
from butler.core.events.event_types import DomainEvent


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


# Global singleton instance (for testing and simple use cases)
_global_event_store: InMemoryEventStore | None = None


def get_global_event_store() -> InMemoryEventStore:
    """Get or create the global event store."""
    global _global_event_store
    if _global_event_store is None:
        _global_event_store = InMemoryEventStore()
    return _global_event_store


def reset_global_event_store() -> None:
    """Reset the global event store (for testing)."""
    global _global_event_store
    _global_event_store = InMemoryEventStore()


__all__ = [
    "EventStore",
    "InMemoryEventStore",
    "get_global_event_store",
    "reset_global_event_store",
]
