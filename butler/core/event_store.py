"""Event store with SQLite persistence and replay capabilities."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from butler.contracts.events import EventType


@dataclass(frozen=True)
class StoredEvent:
    event_id: str
    event_type: str
    payload: Dict[str, Any]
    session_key: str
    timestamp: float
    stored_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


class EventStore:
    """SQLite-backed event store for persistence and replay."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._conn: sqlite3.Connection | None = None
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT NOT NULL,
                payload TEXT NOT NULL,
                session_key TEXT NOT NULL DEFAULT '',
                timestamp REAL NOT NULL,
                stored_at TEXT NOT NULL
            )
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_session_key 
            ON events(session_key)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_event_type 
            ON events(event_type)
            """
        )
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_events_timestamp 
            ON events(timestamp)
            """
        )
        conn.commit()
        conn.close()

    def _get_conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self._db_path))
        return self._conn

    def store(self, event: StoredEvent) -> None:
        """Store a single event."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT OR REPLACE INTO events 
            (event_id, event_type, payload, session_key, timestamp, stored_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                event.event_id,
                event.event_type,
                json.dumps(event.payload, ensure_ascii=False),
                event.session_key,
                event.timestamp,
                event.stored_at.isoformat(),
            ),
        )
        conn.commit()

    def store_batch(self, events: Iterable[StoredEvent]) -> None:
        """Store multiple events in a batch."""
        conn = self._get_conn()
        cursor = conn.cursor()
        rows = []
        for event in events:
            rows.append(
                (
                    event.event_id,
                    event.event_type,
                    json.dumps(event.payload, ensure_ascii=False),
                    event.session_key,
                    event.timestamp,
                    event.stored_at.isoformat(),
                )
            )
        cursor.executemany(
            """
            INSERT OR REPLACE INTO events 
            (event_id, event_type, payload, session_key, timestamp, stored_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            rows,
        )
        conn.commit()

    def query_by_session(
        self, session_key: str, limit: int = 100
    ) -> List[StoredEvent]:
        """Query events by session key."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, event_type, payload, session_key, timestamp, stored_at
            FROM events WHERE session_key = ? ORDER BY timestamp DESC LIMIT ?
            """,
            (session_key, limit),
        )
        return [self._row_to_event(row) for row in cursor.fetchall()]

    def query_by_type(
        self, event_type: str, limit: int = 100
    ) -> List[StoredEvent]:
        """Query events by type."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT event_id, event_type, payload, session_key, timestamp, stored_at
            FROM events WHERE event_type = ? ORDER BY timestamp DESC LIMIT ?
            """,
            (event_type, limit),
        )
        return [self._row_to_event(row) for row in cursor.fetchall()]

    def query_recent(
        self, since_timestamp: float | None = None, limit: int = 100
    ) -> List[StoredEvent]:
        """Query recent events."""
        conn = self._get_conn()
        cursor = conn.cursor()
        if since_timestamp is not None:
            cursor.execute(
                """
                SELECT event_id, event_type, payload, session_key, timestamp, stored_at
                FROM events WHERE timestamp >= ? ORDER BY timestamp ASC LIMIT ?
                """,
                (since_timestamp, limit),
            )
        else:
            cursor.execute(
                """
                SELECT event_id, event_type, payload, session_key, timestamp, stored_at
                FROM events ORDER BY timestamp DESC LIMIT ?
                """,
                (limit,),
            )
        return [self._row_to_event(row) for row in cursor.fetchall()]

    def replay(
        self,
        session_key: str | None = None,
        event_types: Sequence[str] | None = None,
        since_timestamp: float | None = None,
    ) -> Iterable[StoredEvent]:
        """Replay events with optional filters."""
        conn = self._get_conn()
        cursor = conn.cursor()
        conditions = []
        params: List[Any] = []

        if session_key:
            conditions.append("session_key = ?")
            params.append(session_key)
        if event_types:
            placeholders = ",".join("?" * len(event_types))
            conditions.append(f"event_type IN ({placeholders})")
            params.extend(event_types)
        if since_timestamp:
            conditions.append("timestamp >= ?")
            params.append(since_timestamp)

        where_clause = "WHERE " + " AND ".join(conditions) if conditions else ""
        cursor.execute(
            f"""
            SELECT event_id, event_type, payload, session_key, timestamp, stored_at
            FROM events {where_clause} ORDER BY timestamp ASC
            """,
            params,
        )
        for row in cursor.fetchall():
            yield self._row_to_event(row)

    def delete_old(self, older_than_days: int = 30) -> int:
        """Delete events older than specified days."""
        cutoff = time.time() - (older_than_days * 24 * 60 * 60)
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM events WHERE timestamp < ?",
            (cutoff,),
        )
        count = cursor.rowcount
        conn.commit()
        return count

    def count(self) -> int:
        """Get total event count."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM events")
        return cursor.fetchone()[0]

    def count_by_type(self) -> Dict[str, int]:
        """Get event count by type."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("SELECT event_type, COUNT(*) FROM events GROUP BY event_type")
        return {row[0]: row[1] for row in cursor.fetchall()}

    def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            self._conn.close()
            self._conn = None

    def _row_to_event(self, row) -> StoredEvent:
        return StoredEvent(
            event_id=row[0],
            event_type=row[1],
            payload=json.loads(row[2]),
            session_key=row[3],
            timestamp=float(row[4]),
            stored_at=datetime.fromisoformat(row[5]),
        )


def create_default_event_store() -> EventStore:
    """Create event store at default location."""
    data_dir = Path(os.environ.get("BUTLER_DATA_DIR", "./data")) / "events"
    return EventStore(data_dir / "events.db")


# Global event store instance for convenience
_event_store = create_default_event_store()


def append_event(event: Any) -> None:
    """Append a domain event to the event store.
    
    Accepts any event object with:
    - event_id
    - event_type  
    - session_key
    - timestamp
    - to_dict() method
    """
    from butler.core.best_effort import safe_best_effort

    def _store() -> None:
        payload = getattr(event, "to_dict", lambda: event.__dict__)()
        stored = StoredEvent(
            event_id=getattr(event, "event_id", ""),
            event_type=getattr(event, "event_type", ""),
            payload=payload,
            session_key=getattr(event, "session_key", ""),
            timestamp=getattr(event, "timestamp", time.time()),
        )
        _event_store.store(stored)

    safe_best_effort(_store, label="event_store.append_event")


__all__ = ["EventStore", "StoredEvent", "create_default_event_store", "append_event"]