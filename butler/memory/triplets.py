"""Lightweight knowledge triplets (display-only) extracted from memory bullets."""

from __future__ import annotations

import logging
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_RELATION_SEPS = ("是", "为", "采用", "使用", "改为", "位于", "属于", "→", "->")


def extract_triplets_from_text(
    text: str,
    *,
    max_triplets: int = 8,
) -> list[dict[str, str]]:
    """Heuristic (主体, 关系, 客体) from a single memory line or paragraph."""
    out: list[dict[str, str]] = []
    if not (text or "").strip():
        return out
    for raw in re.split(r"[\n；;]+", text):
        line = raw.strip().lstrip("- ").strip()
        if len(line) < 6 or len(line) > 240:
            continue
        for sep in _RELATION_SEPS:
            if sep not in line:
                continue
            left, right = line.split(sep, 1)
            subj = left.strip()[:80]
            obj = right.strip()[:120]
            if subj and obj:
                out.append({"subject": subj, "relation": sep, "object": obj})
            break
        if len(out) >= max_triplets:
            break
    return out[:max_triplets]


class TripletIndex:
    """SQLite store for display-only triplets (same DB file as semantic vectors)."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS memory_triplets (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        project TEXT NOT NULL DEFAULT '',
                        subject TEXT NOT NULL,
                        relation TEXT NOT NULL,
                        object TEXT NOT NULL,
                        source TEXT NOT NULL DEFAULT '',
                        source_ref TEXT NOT NULL DEFAULT '',
                        created_at REAL NOT NULL,
                        UNIQUE(project, subject, relation, object, source_ref)
                    )
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_triplets_project ON memory_triplets(project)"
                )
                conn.commit()

    def upsert_from_content(
        self,
        *,
        content: str,
        project: str = "",
        source: str = "",
        source_ref: str = "",
        max_triplets: int = 6,
    ) -> int:
        triplets = extract_triplets_from_text(content, max_triplets=max_triplets)
        if not triplets:
            return 0
        now = time.time()
        proj = (project or "").strip()
        src = (source or "").strip()
        ref = (source_ref or "").strip()
        added = 0
        with self._lock:
            with self._connect() as conn:
                for t in triplets:
                    try:
                        conn.execute(
                            """
                            INSERT INTO memory_triplets (
                                project, subject, relation, object,
                                source, source_ref, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?)
                            ON CONFLICT(project, subject, relation, object, source_ref)
                            DO UPDATE SET created_at=excluded.created_at
                            """,
                            (
                                proj,
                                t["subject"],
                                t["relation"],
                                t["object"],
                                src,
                                ref,
                                now,
                            ),
                        )
                        added += 1
                    except sqlite3.Error as exc:
                        logger.debug("Triplet upsert skipped: %s", exc)
                conn.commit()
        return added

    def list_recent(
        self,
        *,
        project: str | None = None,
        limit: int = 12,
    ) -> list[dict[str, Any]]:
        cap = max(1, min(int(limit), 50))
        with self._lock:
            with self._connect() as conn:
                if project is not None and str(project).strip():
                    rows = conn.execute(
                        """
                        SELECT subject, relation, object, project, source, source_ref, created_at
                        FROM memory_triplets
                        WHERE project = ? OR project = ''
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (project.strip(), cap),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT subject, relation, object, project, source, source_ref, created_at
                        FROM memory_triplets
                        ORDER BY created_at DESC
                        LIMIT ?
                        """,
                        (cap,),
                    ).fetchall()
        return [
            {
                "subject": r[0],
                "relation": r[1],
                "object": r[2],
                "project": r[3],
                "source": r[4],
                "source_ref": r[5],
                "created_at": r[6],
            }
            for r in rows
        ]

    def clear_all(self) -> int:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute("DELETE FROM memory_triplets")
                conn.commit()
                return int(cur.rowcount or 0)

    def count(self, *, project: str | None = None) -> int:
        with self._lock:
            with self._connect() as conn:
                if project is not None and str(project).strip():
                    row = conn.execute(
                        "SELECT COUNT(*) FROM memory_triplets WHERE project = ? OR project = ''",
                        (project.strip(),),
                    ).fetchone()
                else:
                    row = conn.execute("SELECT COUNT(*) FROM memory_triplets").fetchone()
                return int(row[0] if row else 0)

    def format_display(self, *, project: str | None = None, limit: int = 10) -> str:
        rows = self.list_recent(project=project, limit=limit)
        if not rows:
            return "（暂无三元组；写入 MEMORY/经验后会从「A 采用 B」类句式自动提取）"
        lines = []
        for r in rows:
            proj = (r.get("project") or "").strip()
            tag = f"[{proj}] " if proj else ""
            lines.append(
                f"- {tag}{r['subject']} —{r['relation']}→ {r['object']}"
            )
        return "\n".join(lines)
