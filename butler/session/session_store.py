"""SessionStateStore — SQLite persistence for session state.

Stores serialized conversation state with lifecycle metadata.
Supports: save, load, delete, query, and cleanup of expired sessions.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Optional

logger = logging.getLogger(__name__)


class SessionStateStore:
    _SCHEMA_VERSION = 1

    def __init__(self, db_path: str | None = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
        default_data_dir = os.path.join(project_root, ".wfxm_data")

        self._db_path = db_path or os.path.join(
            default_data_dir, "session_state.db"
        )
        self._lock = threading.RLock()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        os.makedirs(os.path.dirname(self._db_path), exist_ok=True)
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("PRAGMA journal_mode=WAL")
                cursor = conn.cursor()
                cursor.execute("PRAGMA user_version")
                version = cursor.fetchone()[0]

                if version == 0:
                    conn.execute("""
                        CREATE TABLE sessions (
                            session_id TEXT PRIMARY KEY,
                            state TEXT NOT NULL,
                            state_json TEXT NOT NULL,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL,
                            ended_at REAL,
                            last_active_at REAL NOT NULL,
                            reason TEXT,
                            metadata_json TEXT DEFAULT '{}'
                        )
                    """)
                    conn.execute("CREATE INDEX idx_sessions_state ON sessions(state)")
                    conn.execute("CREATE INDEX idx_sessions_updated ON sessions(updated_at DESC)")
                    conn.execute("CREATE INDEX idx_sessions_last_active ON sessions(last_active_at DESC)")
                    conn.execute("CREATE INDEX idx_sessions_ended ON sessions(ended_at)")

                    conn.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
                    conn.commit()

    def save(self, session_id: str, state_data: dict[str, Any], state: str = "running", reason: str = "") -> None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                now = time.time()
                state_json = json.dumps(state_data, ensure_ascii=False)

                conn.execute("""
                    INSERT OR REPLACE INTO sessions (
                        session_id, state, state_json, created_at, updated_at,
                        ended_at, last_active_at, reason, metadata_json
                    ) VALUES (?, ?, ?, COALESCE(
                        (SELECT created_at FROM sessions WHERE session_id = ?), ?
                    ), ?, NULL, ?, ?, '{}')
                """, (session_id, state, state_json, session_id, now, now, now, reason))
                conn.commit()

    def load(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT state_json FROM sessions WHERE session_id = ?",
                    (session_id,)
                )
                row = cursor.fetchone()
                if row:
                    try:
                        return json.loads(row[0])
                    except json.JSONDecodeError:
                        logger.error("Failed to decode session state for %s", session_id)
                        return None
        return None

    def get_session_info(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT session_id, state, created_at, updated_at, ended_at,
                           last_active_at, reason, metadata_json
                    FROM sessions WHERE session_id = ?
                """, (session_id,))
                row = cursor.fetchone()
                if row:
                    return {
                        "session_id": row[0],
                        "state": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "ended_at": row[4],
                        "last_active_at": row[5],
                        "reason": row[6],
                        "metadata": json.loads(row[7]) if row[7] else {},
                    }
        return None

    def update_state(self, session_id: str, new_state: str, reason: str = "") -> bool:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                now = time.time()
                ended_at = now if new_state == "destroyed" else None

                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE sessions
                    SET state = ?, updated_at = ?, ended_at = ?, last_active_at = ?, reason = ?
                    WHERE session_id = ?
                """, (new_state, now, ended_at, now, reason, session_id))
                conn.commit()
                return cursor.rowcount > 0

    def delete(self, session_id: str) -> bool:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM sessions WHERE session_id = ?", (session_id,))
                conn.commit()
                return cursor.rowcount > 0

    def list_sessions(
        self,
        state: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                query = """
                    SELECT session_id, state, created_at, updated_at, last_active_at
                    FROM sessions
                """
                params: list[Any] = []

                if state:
                    query += " WHERE state = ?"
                    params.append(state)

                query += " ORDER BY updated_at DESC LIMIT ? OFFSET ?"
                params.extend([limit, offset])

                cursor.execute(query, params)
                rows = cursor.fetchall()

                return [
                    {
                        "session_id": row[0],
                        "state": row[1],
                        "created_at": row[2],
                        "updated_at": row[3],
                        "last_active_at": row[4],
                    }
                    for row in rows
                ]

    def cleanup_expired(self, max_age_hours: int = 72) -> int:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cutoff = time.time() - (max_age_hours * 3600)
                cursor = conn.cursor()
                cursor.execute("""
                    DELETE FROM sessions
                    WHERE state = 'destroyed' AND ended_at IS NOT NULL AND ended_at < ?
                """, (cutoff,))
                conn.commit()
                return cursor.rowcount

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(*) FROM sessions")
                total = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM sessions WHERE state = 'running'")
                running = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM sessions WHERE state = 'ended'")
                ended = cursor.fetchone()[0]

                cursor.execute("SELECT COUNT(*) FROM sessions WHERE state = 'destroyed'")
                destroyed = cursor.fetchone()[0]

                cursor.execute("SELECT MIN(created_at) FROM sessions")
                oldest = cursor.fetchone()[0]

                cursor.execute("SELECT MAX(updated_at) FROM sessions")
                newest = cursor.fetchone()[0]

                return {
                    "total": total,
                    "running": running,
                    "ended": ended,
                    "destroyed": destroyed,
                    "oldest_session": datetime.fromtimestamp(oldest).isoformat() if oldest else None,
                    "newest_session": datetime.fromtimestamp(newest).isoformat() if newest else None,
                }

    def close(self) -> None:
        pass


_session_store: Optional[SessionStateStore] = None
_session_store_lock = threading.Lock()


def get_session_store() -> SessionStateStore:
    global _session_store
    with _session_store_lock:
        if _session_store is None:
            _session_store = SessionStateStore()
    return _session_store
