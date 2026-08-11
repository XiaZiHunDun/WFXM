"""Hybrid event store combining memory cache and file persistence.

Provides HybridEventStore that:
- Reads from in-memory cache for fast access
- Writes to both memory and file for durability
- Supports automatic recovery from file on startup
"""

from __future__ import annotations

import threading
from typing import Iterable

from butler.core.effects import Result, Ok, Err
from butler.core.events.event_store_protocol import EventStore
from butler.core.events.event_types import DomainEvent
from butler.core.events.file_event_store import FileEventStore


class HybridEventStore:
    """Hybrid event store with memory cache and file persistence.

    Architecture:
    - Write path: Append to memory cache first, then write to file
    - Read path: Return from memory cache (fast)
    - Recovery: Load from file on startup
    """

    def __init__(
        self,
        file_store: FileEventStore | None = None,
        auto_recover: bool = True,
    ) -> None:
        self._file_store = file_store or FileEventStore()
        self._lock = threading.RLock()
        self._events_by_session: dict[str, list[DomainEvent]] = {}
        self._events_by_id: dict[str, DomainEvent] = {}

        if auto_recover:
            self._recover_from_file()

    def _recover_from_file(self) -> None:
        """Recover all events from file storage on startup."""
        result = self._file_store.get_all_sessions()
        if result.is_err():
            return

        for session_key in result.unwrap():
            events_result = self._file_store.get_events_for_session(session_key)
            if events_result.is_ok():
                for event in events_result.unwrap():
                    self._cache_event(event)

    def _cache_event(self, event: DomainEvent) -> None:
        """Cache an event in memory."""
        if event.session_key not in self._events_by_session:
            self._events_by_session[event.session_key] = []
        self._events_by_session[event.session_key].append(event)
        self._events_by_id[event.event_id] = event

    def append(self, event: DomainEvent) -> Result[None, Exception]:
        """Append an event to both memory and file."""
        try:
            with self._lock:
                # Cache in memory first (fast path)
                self._cache_event(event)

            # Write to file (may be async-safe since we already cached)
            file_result = self._file_store.append(event)
            if file_result.is_err():
                # Roll back memory cache on file failure
                with self._lock:
                    if event.session_key in self._events_by_session:
                        self._events_by_session[event.session_key] = [
                            e
                            for e in self._events_by_session[event.session_key]
                            if e.event_id != event.event_id
                        ]
                    self._events_by_id.pop(event.event_id, None)
                return file_result

            return Ok(None)
        except Exception as e:
            return Err(e)

    def append_batch(self, events: Iterable[DomainEvent]) -> Result[None, Exception]:
        """Append multiple events atomically."""
        try:
            with self._lock:
                for event in events:
                    self._cache_event(event)

            # Write to file
            file_result = self._file_store.append_batch(events)
            if file_result.is_err():
                # Roll back on failure
                with self._lock:
                    event_ids = {e.event_id for e in events}
                    for session_key in self._events_by_session:
                        self._events_by_session[session_key] = [
                            e
                            for e in self._events_by_session[session_key]
                            if e.event_id not in event_ids
                        ]
                    for eid in event_ids:
                        self._events_by_id.pop(eid, None)
                return file_result

            return Ok(None)
        except Exception as e:
            return Err(e)

    def get_events_for_session(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Get all events for a session (from memory cache)."""
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
        result = self.get_events_for_session(session_key)
        if result.is_err():
            return result
        filtered = [e for e in result.unwrap() if e.event_type == event_type]
        return Ok(filtered)

    def get_event(self, event_id: str) -> Result[DomainEvent | None, Exception]:
        """Get a single event by ID (from memory cache)."""
        try:
            with self._lock:
                event = self._events_by_id.get(event_id)
                if event is not None:
                    return Ok(event)
            # Fallback to file store
            return self._file_store.get_event(event_id)
        except Exception as e:
            return Err(e)

    def replay(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Replay all events for a session in order."""
        return self.get_events_for_session(session_key)

    def clear_session(self, session_key: str) -> Result[None, Exception]:
        """Remove all events for a session (from both memory and file)."""
        try:
            with self._lock:
                if session_key in self._events_by_session:
                    for event in self._events_by_session[session_key]:
                        self._events_by_id.pop(event.event_id, None)
                    del self._events_by_session[session_key]
            return self._file_store.clear_session(session_key)
        except Exception as e:
            return Err(e)

    def get_all_sessions(self) -> Result[list[str], Exception]:
        """Get all session keys (from memory cache)."""
        try:
            with self._lock:
                return Ok(list(self._events_by_session.keys()))
        except Exception as e:
            return Err(e)

    def count_events(self) -> Result[int, Exception]:
        """Count all events (from memory cache)."""
        try:
            with self._lock:
                return Ok(sum(len(events) for events in self._events_by_session.values()))
        except Exception as e:
            return Err(e)

    def sync_from_file(self, session_key: str) -> Result[int, Exception]:
        """Synchronize a session's events from file to memory."""
        try:
            result = self._file_store.get_events_for_session(session_key)
            if result.is_err():
                return result

            events = result.unwrap()
            with self._lock:
                # Clear existing cache for this session
                if session_key in self._events_by_session:
                    for event in self._events_by_session[session_key]:
                        self._events_by_id.pop(event.event_id, None)

                # Load from file
                self._events_by_session[session_key] = []
                for event in events:
                    self._cache_event(event)

            return Ok(len(events))
        except Exception as e:
            return Err(e)

    @property
    def file_store(self) -> FileEventStore:
        """Access the underlying file store."""
        return self._file_store


__all__ = [
    "HybridEventStore",
]
