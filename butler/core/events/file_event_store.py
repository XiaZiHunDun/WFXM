"""File-based event store persistence.

Provides FileEventStore for persistent event storage using JSON files.
Each session's events are stored in a separate JSONL file for efficiency.

Usage:
    store = FileEventStore(base_dir="/path/to/event_store")
    store.append(event)
    events = store.get_events_for_session("session-key")
"""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Iterable

from butler.core.effects import Result, Ok, Err
from butler.core.events.event_types import DomainEvent


class FileEventStore:
    """File-based persistent event store.

    Stores events as JSONL files, one file per session.
    Provides thread-safe append and read operations.
    """

    def __init__(self, base_dir: str | Path | None = None) -> None:
        if base_dir is None:
            base_dir = os.environ.get(
                "BUTLER_EVENT_STORE_DIR",
                str(Path.home() / ".butler" / "events"),
            )
        self._base_dir = Path(base_dir)
        self._base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._session_locks: dict[str, threading.Lock] = {}

    def _get_session_path(self, session_key: str) -> Path:
        """Get the file path for a session's events."""
        safe_key = session_key.replace(":", "_").replace("/", "_")
        return self._base_dir / f"{safe_key}.jsonl"

    def _get_session_lock(self, session_key: str) -> threading.Lock:
        """Get or create a per-session lock."""
        with self._lock:
            if session_key not in self._session_locks:
                self._session_locks[session_key] = threading.Lock()
            return self._session_locks[session_key]

    def _serialize_event(self, event: DomainEvent) -> dict:
        """Serialize an event to a JSON-compatible dict."""
        return {
            "event_id": event.event_id,
            "event_type": event.event_type,
            "session_key": event.session_key,
            "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            "data": event.data,
            "version": event.version,
            "metadata": event.metadata,
            # Extra fields for specific event types
            **{
                k: v
                for k, v in vars(event).items()
                if k
                not in {
                    "event_id",
                    "event_type",
                    "session_key",
                    "timestamp",
                    "data",
                    "version",
                    "metadata",
                }
            },
        }

    def _deserialize_event(self, data: dict) -> DomainEvent | None:
        """Deserialize a dict back to a DomainEvent subclass."""
        try:
            # Try to reconstruct by looking at event_type
            event_type = data.get("event_type", "")

            # Map event types to classes
            from butler.core.events.session_events import (
                SESSION_STARTED,
                SESSION_ENDED,
                TOOL_CALLED,
                TOOL_COMPLETED,
                TOOL_FAILED,
                APPROVAL_REQUESTED,
                APPROVAL_GRANTED,
                APPROVAL_DENIED,
                SessionStarted,
                SessionEnded,
                ToolCalled,
                ToolCompleted,
                ToolFailedEvent,
                ApprovalRequested,
                ApprovalGranted,
                ApprovalDenied,
            )

            type_map: dict[str, type[DomainEvent]] = {
                "SESSION_STARTED.1": SessionStarted,
                "SESSION_ENDED.1": SessionEnded,
                "TOOL_CALLED.1": ToolCalled,
                "TOOL_COMPLETED.1": ToolCompleted,
                "TOOL_FAILED.1": ToolFailedEvent,
                "APPROVAL_REQUESTED.1": ApprovalRequested,
                "APPROVAL_GRANTED.1": ApprovalGranted,
                "APPROVAL_DENIED.1": ApprovalDenied,
            }

            # Remove serialization-only fields
            clean_data = {
                k: v
                for k, v in data.items()
                if k
                not in {
                    "event_id",
                    "event_type",
                    "session_key",
                    "timestamp",
                    "data",
                    "version",
                    "metadata",
                }
            }

            event_class = type_map.get(event_type)
            if event_class is None:
                # Generic DomainEvent
                from butler.core.events.event_types import DomainEvent as GenericEvent

                ts = data.get("timestamp")
                if ts:
                    from datetime import datetime, timezone

                    timestamp = datetime.fromisoformat(ts)
                else:
                    timestamp = datetime.now(timezone.utc)

                return GenericEvent(
                    event_id=data.get("event_id", ""),
                    event_type=event_type,
                    session_key=data.get("session_key", ""),
                    timestamp=timestamp,
                    data=data.get("data", {}),
                    version=data.get("version", 1),
                    metadata=data.get("metadata", {}),
                )

            # Reconstruct specific event type
            ts = data.get("timestamp")
            if ts:
                from datetime import datetime, timezone

                timestamp = datetime.fromisoformat(ts)
            else:
                from datetime import datetime, timezone

                timestamp = datetime.now(timezone.utc)

            return event_class(
                event_id=data.get("event_id", ""),
                event_type=event_type,
                session_key=data.get("session_key", ""),
                timestamp=timestamp,
                data=data.get("data", {}),
                version=data.get("version", 1),
                metadata=data.get("metadata", {}),
                **clean_data,
            )
        except Exception:
            return None

    def append(self, event: DomainEvent) -> Result[None, Exception]:
        """Append an event to the session's file."""
        try:
            session_key = event.session_key
            if not session_key:
                return Err(ValueError("Event has no session_key"))

            session_path = self._get_session_path(session_key)
            session_lock = self._get_session_lock(session_key)

            with session_lock:
                serialized = self._serialize_event(event)
                line = json.dumps(serialized, ensure_ascii=False) + "\n"

                with open(session_path, "a", encoding="utf-8") as f:
                    f.write(line)
                    f.flush()

            return Ok(None)
        except Exception as e:
            return Err(e)

    def append_batch(self, events: Iterable[DomainEvent]) -> Result[None, Exception]:
        """Append multiple events atomically (within a session)."""
        try:
            # Group events by session
            by_session: dict[str, list[DomainEvent]] = {}
            for event in events:
                key = event.session_key
                if not key:
                    return Err(ValueError("Event has no session_key"))
                if key not in by_session:
                    by_session[key] = []
                by_session[key].append(event)

            # Write each session's events
            for session_key, session_events in by_session.items():
                session_path = self._get_session_path(session_key)
                session_lock = self._get_session_lock(session_key)

                with session_lock:
                    with open(session_path, "a", encoding="utf-8") as f:
                        for event in session_events:
                            serialized = self._serialize_event(event)
                            line = json.dumps(serialized, ensure_ascii=False) + "\n"
                            f.write(line)
                        f.flush()

            return Ok(None)
        except Exception as e:
            return Err(e)

    def get_events_for_session(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Get all events for a session, ordered by timestamp."""
        try:
            session_path = self._get_session_path(session_key)
            if not session_path.exists():
                return Ok([])

            events: list[DomainEvent] = []
            with open(session_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        event = self._deserialize_event(data)
                        if event is not None:
                            events.append(event)
                    except (json.JSONDecodeError, Exception):
                        continue

            # Sort by timestamp
            events.sort(key=lambda e: e.timestamp if e.timestamp else datetime.min)
            return Ok(events)
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
        """Get a single event by ID (scans all sessions)."""
        try:
            for session_file in self._base_dir.glob("*.jsonl"):
                with open(session_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            data = json.loads(line)
                            if data.get("event_id") == event_id:
                                event = self._deserialize_event(data)
                                return Ok(event)
                        except (json.JSONDecodeError, Exception):
                            continue
            return Ok(None)
        except Exception as e:
            return Err(e)

    def replay(self, session_key: str) -> Result[list[DomainEvent], Exception]:
        """Replay all events for a session in order."""
        return self.get_events_for_session(session_key)

    def clear_session(self, session_key: str) -> Result[None, Exception]:
        """Remove all events for a session."""
        try:
            session_path = self._get_session_path(session_key)
            if session_path.exists():
                session_lock = self._get_session_lock(session_key)
                with session_lock:
                    session_path.unlink()
            return Ok(None)
        except Exception as e:
            return Err(e)

    def get_all_sessions(self) -> Result[list[str], Exception]:
        """Get all session keys with stored events."""
        try:
            sessions = []
            for session_file in self._base_dir.glob("*.jsonl"):
                # Convert filename back to session key
                stem = session_file.stem
                session_key = stem.replace("_", ":")
                sessions.append(session_key)
            return Ok(sessions)
        except Exception as e:
            return Err(e)

    def count_events(self) -> Result[int, Exception]:
        """Count all events across all sessions."""
        try:
            total = 0
            for session_file in self._base_dir.glob("*.jsonl"):
                with open(session_file, "r", encoding="utf-8") as f:
                    total += sum(1 for line in f if line.strip())
            return Ok(total)
        except Exception as e:
            return Err(e)

    def get_session_file_path(self, session_key: str) -> Path:
        """Get the file path for a session's events (for inspection)."""
        return self._get_session_path(session_key)

    def get_base_dir(self) -> Path:
        """Get the base directory for event storage."""
        return self._base_dir


__all__ = [
    "FileEventStore",
]
