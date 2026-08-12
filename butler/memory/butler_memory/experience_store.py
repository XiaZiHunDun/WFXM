from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, cast

from butler.memory.butler_memory_ops import close_sqlite_connection
from butler.memory.retrieval_ranking import rerank_memory_hits

_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|system prompt|you are now|forget everything|\[\[INST\]\])",
    re.IGNORECASE,
)


def _reject_injection(content: str) -> bool:
    return bool(_INJECTION_PATTERNS.search(content))


class ExperienceStore:
    """SQLite + FTS5 for cross-project experience."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._conn = self._open_conn()
        self._init_db()

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def close(self) -> None:
        with self._lock:
            close_sqlite_connection(self._conn)

    def _init_db(self) -> None:
        with self._lock:
            conn = self._conn
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS experiences (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    tags TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS experiences_fts
                USING fts5(
                    content,
                    category,
                    tags,
                    project,
                    tokenize='porter unicode61'
                )
                """
            )
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS exp_fts_ai AFTER INSERT ON experiences BEGIN
                    INSERT INTO experiences_fts(rowid, content, category, tags, project)
                    VALUES (new.id, new.content, new.category, new.tags, new.project);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS exp_fts_ad AFTER DELETE ON experiences BEGIN
                    DELETE FROM experiences_fts WHERE rowid = old.id;
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS exp_fts_au AFTER UPDATE ON experiences BEGIN
                    DELETE FROM experiences_fts WHERE rowid = old.id;
                    INSERT INTO experiences_fts(rowid, content, category, tags, project)
                    VALUES (new.id, new.content, new.category, new.tags, new.project);
                END
            """)
            self._ensure_experience_columns(conn)
            conn.commit()

    def _ensure_experience_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(experiences)").fetchall()}
        if "access_count" not in cols:
            conn.execute(
                "ALTER TABLE experiences ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"
            )
        if "last_accessed_at" not in cols:
            conn.execute(
                "ALTER TABLE experiences ADD COLUMN last_accessed_at REAL NOT NULL DEFAULT 0"
            )

    def record_access(self, row_ids: list[int]) -> None:
        ids = [int(x) for x in row_ids if x is not None]
        if not ids:
            return
        now = time.time()
        with self._lock:
            conn = self._conn
            for rid in ids:
                conn.execute(
                    """
                    UPDATE experiences
                    SET access_count = access_count + 1, last_accessed_at = ?
                    WHERE id = ?
                    """,
                    (now, rid),
                )
            conn.commit()

    def add(
        self,
        project: str,
        category: str,
        content: str,
        tags: str | list[str] | None = None,
    ) -> int:
        if _reject_injection(content or ""):
            return -1
        tag_str = ""
        if tags is None:
            tag_str = ""
        elif isinstance(tags, list):
            tag_str = ",".join(t.strip() for t in tags if str(t).strip())
        else:
            tag_str = tags.strip()

        now = time.time()
        with self._lock:
            conn = self._conn
            cur = conn.execute(
                """
                INSERT INTO experiences (project, category, content, tags, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (project or "", category or "", content, tag_str, now),
            )
            conn.commit()
            return int(cur.lastrowid or 0)

    def update_content(
        self,
        row_id: int,
        content: str,
        *,
        tags: str | list[str] | None = None,
    ) -> bool:
        if _reject_injection(content or ""):
            return False
        if row_id <= 0:
            return False
        tag_str: str | None = None
        if tags is not None:
            if isinstance(tags, list):
                tag_str = ",".join(t.strip() for t in tags if str(t).strip())
            else:
                tag_str = str(tags).strip()

        with self._lock:
            conn = self._conn
            if tag_str is not None:
                cur = conn.execute(
                    "UPDATE experiences SET content = ?, tags = ? WHERE id = ?",
                    (content, tag_str, row_id),
                )
            else:
                cur = conn.execute(
                    "UPDATE experiences SET content = ? WHERE id = ?",
                    (content, row_id),
                )
            conn.commit()
            return int(cur.rowcount or 0) > 0

    def search(
        self,
        query: str,
        project: str | None = None,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        q = (query or "").strip()
        if not q:
            return []
        phrase = '"' + q.replace('"', '""') + '"'
        with self._lock:
            conn = self._conn
            try:
                if project is not None and str(project).strip() != "":
                    rows = conn.execute(
                        """
                        SELECT e.id, e.project, e.category, e.content, e.tags, e.created_at,
                               e.access_count, e.last_accessed_at,
                               bm25(experiences_fts) AS rank
                        FROM experiences e
                        JOIN experiences_fts ON experiences_fts.rowid = e.id
                        WHERE experiences_fts MATCH ? AND e.project = ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (phrase, project, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT e.id, e.project, e.category, e.content, e.tags, e.created_at,
                               e.access_count, e.last_accessed_at,
                               bm25(experiences_fts) AS rank
                        FROM experiences e
                        JOIN experiences_fts ON experiences_fts.rowid = e.id
                        WHERE experiences_fts MATCH ?
                        ORDER BY rank
                        LIMIT ?
                        """,
                        (phrase, limit),
                    ).fetchall()
            except sqlite3.OperationalError:
                like = f"%{q}%"
                if project is not None and str(project).strip() != "":
                    rows = conn.execute(
                        """
                        SELECT id, project, category, content, tags, created_at,
                               COALESCE(access_count, 0), COALESCE(last_accessed_at, 0), 0
                        FROM experiences
                        WHERE content LIKE ? AND project = ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (like, project, limit),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT id, project, category, content, tags, created_at,
                               COALESCE(access_count, 0), COALESCE(last_accessed_at, 0), 0
                        FROM experiences
                        WHERE content LIKE ?
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (like, limit),
                    ).fetchall()

            out: list[dict[str, Any]] = []
            for r in rows:
                item: dict[str, Any] = {
                    "id": r[0],
                    "project": r[1],
                    "category": r[2],
                    "content": r[3],
                    "tags": r[4],
                    "created_at": r[5],
                }
                if len(r) >= 9:
                    item["access_count"] = int(r[6] or 0)
                    item["last_accessed_at"] = float(r[7] or 0)
                    rank = r[8]
                elif len(r) >= 7:
                    item["access_count"] = 0
                    item["last_accessed_at"] = 0.0
                    rank = r[6]
                else:
                    item["access_count"] = 0
                    item["last_accessed_at"] = 0.0
                    rank = 0
                try:
                    item["score"] = 1.0 / (1.0 + abs(float(rank)))
                except (TypeError, ValueError):
                    item["score"] = 0.5
                out.append(item)

            return cast(list[dict[str, Any]], rerank_memory_hits(out))

    def delete_conversation_for_session(self, session_tag: str) -> tuple[int, list[int]]:
        tag = (session_tag or "").strip()
        with self._lock:
            conn = self._conn
            if tag:
                rows = conn.execute(
                    """
                    SELECT id FROM experiences
                    WHERE category = ? AND (tags = ? OR tags = '')
                    """,
                    ("conversation", tag),
                ).fetchall()
                ids = [int(r[0]) for r in rows]
                cur = conn.execute(
                    """
                    DELETE FROM experiences
                    WHERE category = ? AND (tags = ? OR tags = '')
                    """,
                    ("conversation", tag),
                )
            else:
                rows = conn.execute(
                    "SELECT id FROM experiences WHERE category = ?",
                    ("conversation",),
                ).fetchall()
                ids = [int(r[0]) for r in rows]
                cur = conn.execute(
                    "DELETE FROM experiences WHERE category = ?",
                    ("conversation",),
                )
            conn.commit()
            return int(cur.rowcount or 0), ids

    def purge_benchmark_capacity_entries(self) -> list[int]:
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                """
                SELECT id FROM experiences
                WHERE project = ? AND category = ?
                """,
                ("bench", "cap"),
            ).fetchall()
            ids = [int(r[0]) for r in rows]
            if not ids:
                return []
            placeholders = ",".join("?" * len(ids))
            conn.execute(
                f"DELETE FROM experiences WHERE id IN ({placeholders})",
                ids,
            )
            conn.commit()
            return ids

    def has_tag_substring(self, needle: str) -> bool:
        tag = (needle or "").strip()
        if not tag:
            return False
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM experiences WHERE tags LIKE ? LIMIT 1",
                (f"%{tag}%",),
            ).fetchone()
            return row is not None

    def prune_conversation_older_than(self, max_age_days: float = 30.0) -> tuple[int, list[int]]:
        cutoff = time.time() - max(1.0, float(max_age_days)) * 86400.0
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                """
                SELECT id FROM experiences
                WHERE category = ? AND created_at < ?
                """,
                ("conversation", cutoff),
            ).fetchall()
            ids = [int(r[0]) for r in rows]
            if not ids:
                return 0, []
            cur = conn.execute(
                """
                DELETE FROM experiences
                WHERE category = ? AND created_at < ?
                """,
                ("conversation", cutoff),
            )
            conn.commit()
            return int(cur.rowcount or 0), ids

    def fetch_by_ids(self, row_ids: list[int]) -> list[dict[str, Any]]:
        ids = [int(x) for x in row_ids if x is not None]
        if not ids:
            return []
        placeholders = ",".join("?" * len(ids))
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                f"""
                SELECT id, project, category, content, tags, created_at,
                       COALESCE(access_count, 0), COALESCE(last_accessed_at, 0)
                FROM experiences
                WHERE id IN ({placeholders})
                ORDER BY created_at DESC
                """,
                ids,
            ).fetchall()
        out: list[dict[str, Any]] = []
        for r in rows:
            out.append(
                {
                    "id": r[0],
                    "project": r[1],
                    "category": r[2],
                    "content": r[3],
                    "tags": r[4],
                    "created_at": r[5],
                    "access_count": int(r[6] or 0),
                    "last_accessed_at": float(r[7] or 0),
                }
            )
        return out

    def timeline_around(
        self,
        anchor_id: int,
        *,
        before: int = 5,
        after: int = 5,
    ) -> list[dict[str, Any]]:
        aid = int(anchor_id)
        with self._lock:
            conn = self._conn
            row = conn.execute(
                "SELECT created_at, project FROM experiences WHERE id = ?",
                (aid,),
            ).fetchone()
            if not row:
                return []
            created_at, project = float(row[0]), str(row[1] or "")
            older = conn.execute(
                """
                SELECT id, project, category, content, tags, created_at
                FROM experiences
                WHERE project = ? AND created_at <= ? AND id != ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (project, created_at, aid, before),
            ).fetchall()
            newer = conn.execute(
                """
                SELECT id, project, category, content, tags, created_at
                FROM experiences
                WHERE project = ? AND created_at >= ? AND id != ?
                ORDER BY created_at ASC
                LIMIT ?
                """,
                (project, created_at, aid, after),
            ).fetchall()
            anchor = conn.execute(
                """
                SELECT id, project, category, content, tags, created_at
                FROM experiences WHERE id = ?
                """,
                (aid,),
            ).fetchone()
        def _row_dict(r: tuple[Any, ...]) -> dict[str, Any]:
            return {
                "id": r[0],
                "project": r[1],
                "category": r[2],
                "content": r[3],
                "tags": r[4],
                "created_at": r[5],
            }

        combined = list(reversed(older)) + ([_row_dict(anchor)] if anchor else []) + list(newer)
        return combined

    def get_recent(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            conn = self._conn
            rows = conn.execute(
                """
                SELECT id, project, category, content, tags, created_at
                FROM experiences
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        return [
            {
                "id": r[0],
                "project": r[1],
                "category": r[2],
                "content": r[3],
                "tags": r[4],
                "created_at": r[5],
            }
            for r in rows
        ]
