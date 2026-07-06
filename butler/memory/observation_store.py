"""SQLite-backed workspace observation store."""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from butler.memory_settings import resolve_memory_config

_SCHEMA_VERSION = 2


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
                    CREATE TABLE IF NOT EXISTS observation_meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL DEFAULT ''
                    );
                    """
                )
                self._migrate_schema_locked(conn)
                self._prune_locked(conn)
                conn.commit()

    def _migrate_schema_locked(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT value FROM observation_meta WHERE key = 'schema_version'"
        ).fetchone()
        current = 0
        if row is not None:
            try:
                current = int(row["value"] or 0)
            except (TypeError, ValueError):
                current = 0
        if current >= _SCHEMA_VERSION:
            return
        conn.executescript(
            """
            DELETE FROM observations
            WHERE row_id IN (
                SELECT row_id
                FROM (
                    SELECT
                        row_id,
                        ROW_NUMBER() OVER (
                            PARTITION BY session_key, tool, path, content_hash
                            ORDER BY timestamp DESC, row_id DESC
                        ) AS rn
                    FROM observations
                    WHERE content_hash != ''
                )
                WHERE rn > 1
            );
                    DROP INDEX IF EXISTS idx_observations_dedupe;
                    CREATE UNIQUE INDEX IF NOT EXISTS idx_observations_dedupe
                    ON observations(session_key, tool, path, content_hash)
                    WHERE content_hash != '';
            """
        )
        conn.execute(
            """
            INSERT INTO observation_meta(key, value) VALUES ('schema_version', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (str(_SCHEMA_VERSION),),
        )

    @staticmethod
    def _ttl_days() -> int:
        return int(resolve_memory_config().observation_ttl_days)

    @staticmethod
    def _max_rows() -> int:
        return int(resolve_memory_config().observation_max_rows)

    def _prune_locked(self, conn: sqlite3.Connection) -> None:
        ttl_days = self._ttl_days()
        if ttl_days > 0:
            cutoff = (datetime.now(timezone.utc) - timedelta(days=ttl_days)).isoformat()
            conn.execute(
                "DELETE FROM observations WHERE timestamp != '' AND timestamp < ?",
                (cutoff,),
            )
        max_rows = self._max_rows()
        if max_rows > 0:
            conn.execute(
                """
                DELETE FROM observations
                WHERE row_id IN (
                    SELECT row_id
                    FROM observations
                    ORDER BY timestamp DESC, row_id DESC
                    LIMIT -1 OFFSET ?
                )
                """,
                (max_rows,),
            )

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
                self._prune_locked(conn)
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

    def search(self, query: str, *, limit: int = 8) -> list[dict[str, str]]:
        """Keyword search over preview/title/path/tool (recency-weighted)."""
        q = str(query or "").strip().lower()
        if len(q) < 2:
            return []
        cap = max(1, min(50, int(limit or 8)))
        like = f"%{q.replace('%', '').replace('_', '')}%"
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT row_id, timestamp, session_key, tool, ok, path, preview, title, content_hash
                    FROM observations
                    WHERE lower(preview) LIKE ?
                       OR lower(title) LIKE ?
                       OR lower(path) LIKE ?
                       OR lower(tool) LIKE ?
                    ORDER BY timestamp DESC, row_id DESC
                    LIMIT ?
                    """,
                    (like, like, like, like, max(cap * 4, 20)),
                ).fetchall()
        if not rows:
            return []
        now = datetime.now(timezone.utc)
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            preview = str(row["preview"] or "")
            title = str(row["title"] or "")
            path = str(row["path"] or "")
            tool = str(row["tool"] or "")
            blob = f"{preview} {title} {path} {tool}".lower()
            if q not in blob:
                continue
            score = 1.0
            if q in preview.lower():
                score += 0.4
            if q in path.lower():
                score += 0.25
            ts_raw = str(row["timestamp"] or "")
            try:
                ts = datetime.fromisoformat(ts_raw.replace("Z", "+00:00"))
                if ts.tzinfo is None:
                    ts = ts.replace(tzinfo=timezone.utc)
                age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
                score *= max(0.35, 1.0 - age_days / 90.0)
            except ValueError:
                pass
            if int(row["ok"] or 0):
                score += 0.05
            item = {
                "row_id": str(row["row_id"] or ""),
                "timestamp": ts_raw,
                "session_key": str(row["session_key"] or ""),
                "tool": tool,
                "ok": "1" if int(row["ok"] or 0) else "0",
                "path": path,
                "preview": preview,
                "title": title,
                "content_hash": str(row["content_hash"] or ""),
                "score": round(score, 4),
            }
            ranked.append((score, item))
        ranked.sort(key=lambda pair: pair[0], reverse=True)
        return [item for _, item in ranked[:cap]]

    def stats(self) -> dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                row_count = int(
                    conn.execute("SELECT COUNT(*) FROM observations").fetchone()[0]
                )
                distinct_paths = int(
                    conn.execute(
                        "SELECT COUNT(DISTINCT path) FROM observations WHERE path != ''"
                    ).fetchone()[0]
                )
                ok_count = int(
                    conn.execute("SELECT COUNT(*) FROM observations WHERE ok = 1").fetchone()[0]
                )
                fail_count = int(
                    conn.execute("SELECT COUNT(*) FROM observations WHERE ok = 0").fetchone()[0]
                )
                oldest = conn.execute(
                    "SELECT MIN(timestamp) FROM observations WHERE timestamp != ''"
                ).fetchone()[0]
                newest = conn.execute(
                    "SELECT MAX(timestamp) FROM observations WHERE timestamp != ''"
                ).fetchone()[0]
                tool_rows = conn.execute(
                    """
                    SELECT tool, COUNT(*) AS cnt
                    FROM observations
                    WHERE tool != ''
                    GROUP BY tool
                    ORDER BY cnt DESC, tool ASC
                    """
                ).fetchall()
        return {
            "row_count": row_count,
            "distinct_paths": distinct_paths,
            "ok_count": ok_count,
            "fail_count": fail_count,
            "oldest_timestamp": str(oldest or ""),
            "newest_timestamp": str(newest or ""),
            "tool_counts": {str(row["tool"]): int(row["cnt"]) for row in tool_rows},
            "db_path": str(self.db_path),
        }


__all__ = ["ObservationStore", "observations_db_path"]
