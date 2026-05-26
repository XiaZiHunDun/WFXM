"""SQLite-backed workspace observation store."""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path


def observations_db_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / "observations.db"


class ObservationStore:
    """Small SQLite store for tool observations scoped to one workspace."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS observations (
                        row_id TEXT PRIMARY KEY,
                        timestamp TEXT NOT NULL,
                        session_key TEXT NOT NULL DEFAULT '',
                        tool TEXT NOT NULL DEFAULT '',
                        ok INTEGER NOT NULL DEFAULT 0,
                        path TEXT NOT NULL DEFAULT '',
                        preview TEXT NOT NULL DEFAULT '',
                        title TEXT NOT NULL DEFAULT '',
                        content_hash TEXT NOT NULL DEFAULT ''
                    );
                    CREATE INDEX IF NOT EXISTS idx_observations_path_ts
                    ON observations(path, timestamp DESC);
                    CREATE INDEX IF NOT EXISTS idx_observations_session_ts
                    ON observations(session_key, timestamp DESC);
                    """
                )
                conn.commit()

    @staticmethod
    def _normalize_row(row: dict[str, str]) -> tuple[str, str, str, str, int, str, str, str, str]:
        return (
            str(row.get("row_id") or "").strip(),
            str(row.get("timestamp") or "").strip(),
            str(row.get("session_key") or "").strip(),
            str(row.get("tool") or "").strip(),
            1 if str(row.get("ok") or "").strip() in {"1", "true", "True"} else 0,
            str(row.get("path") or "").strip().replace("\\", "/"),
            str(row.get("preview") or "").strip(),
            str(row.get("title") or "").strip(),
            str(row.get("content_hash") or "").strip(),
        )

    def insert_many(self, rows: list[dict[str, str]]) -> int:
        payload = [self._normalize_row(row) for row in rows if str(row.get("row_id") or "").strip()]
        if not payload:
            return 0
        with self._lock:
            with self._connect() as conn:
                conn.executemany(
                    """
                    INSERT OR REPLACE INTO observations (
                        row_id, timestamp, session_key, tool, ok, path, preview, title, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    payload,
                )
                conn.commit()
        return len(payload)

    def list_for_path(self, file_path: str, *, limit: int = 5) -> list[dict[str, str]]:
        norm = str(file_path or "").strip().replace("\\", "/")
        if not norm:
            return []
        cap = max(1, int(limit or 5))
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT row_id, timestamp, session_key, tool, ok, path, preview, title, content_hash
                    FROM observations
                    WHERE path != ''
                      AND (? LIKE '%' || path || '%' OR path LIKE '%' || ? || '%')
                    ORDER BY timestamp DESC, row_id DESC
                    LIMIT ?
                    """,
                    (norm, norm, cap),
                ).fetchall()
        result = [
            {
                "row_id": str(row["row_id"] or ""),
                "timestamp": str(row["timestamp"] or ""),
                "session_key": str(row["session_key"] or ""),
                "tool": str(row["tool"] or ""),
                "ok": "1" if int(row["ok"] or 0) else "0",
                "path": str(row["path"] or ""),
                "preview": str(row["preview"] or ""),
                "title": str(row["title"] or ""),
                "content_hash": str(row["content_hash"] or ""),
            }
            for row in rows
        ]
        result.reverse()
        return result


__all__ = ["ObservationStore", "observations_db_path"]
