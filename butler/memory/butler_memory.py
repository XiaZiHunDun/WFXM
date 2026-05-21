"""Butler-level (global) memory: owner profile and cross-project experience."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import tempfile
import threading
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|system prompt|you are now|forget everything|\[\[INST\]\])",
    re.IGNORECASE,
)


def _reject_injection(content: str) -> bool:
    return bool(_INJECTION_PATTERNS.search(content))


class ProfileStore:
    """Bounded free-text store (owner profile, preferences, communication style)."""

    def __init__(self, path: Path, char_limit: int = 2000):
        self.path = Path(path)
        self.char_limit = char_limit
        self._lock = threading.Lock()
        self._entries: list[str] = []
        self.load()

    def load(self) -> None:
        with self._lock:
            if self.path.exists():
                try:
                    data = json.loads(self.path.read_text(encoding="utf-8"))
                    entries = data.get("entries", [])
                    self._entries = [str(e).strip() for e in entries if str(e).strip()]
                except (json.JSONDecodeError, OSError):
                    self._entries = []
            else:
                self._entries = []

    def _save_unlocked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"entries": self._entries}, ensure_ascii=False, indent=2)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(payload)
                f.flush()
                os.fsync(f.fileno())
            os.replace(tmp, self.path)
        except BaseException:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise

    @property
    def total_chars(self) -> int:
        with self._lock:
            return sum(len(e) for e in self._entries)

    def add(self, content: str) -> dict[str, Any]:
        if _reject_injection(content):
            return {"success": False, "error": "Content rejected (suspicious pattern)"}
        content = content.strip()
        if not content:
            return {"success": False, "error": "Empty content"}
        with self._lock:
            if sum(len(e) for e in self._entries) + len(content) > self.char_limit:
                total = sum(len(e) for e in self._entries) + len(content)
                return {
                    "success": False,
                    "error": f"Exceeds character limit ({total}/{self.char_limit}); remove content first",
                }
            self._entries.append(content)
            self._save_unlocked()
        return {"success": True}

    def replace(self, content: str) -> dict[str, Any]:
        """Replace the entire profile with the given text (single entry)."""
        if _reject_injection(content):
            return {"success": False, "error": "Content rejected (suspicious pattern)"}
        content = content.strip()
        if len(content) > self.char_limit:
            return {
                "success": False,
                "error": f"Exceeds character limit ({len(content)}/{self.char_limit})",
            }
        with self._lock:
            self._entries = [content] if content else []
            self._save_unlocked()
        return {"success": True}

    def remove(self, keyword: str) -> dict[str, Any]:
        if not keyword.strip():
            return {"success": False, "error": "Empty keyword"}
        key = keyword.strip()
        with self._lock:
            for i, entry in enumerate(self._entries):
                if key in entry:
                    remaining = entry.replace(key, "").strip()
                    if remaining:
                        self._entries[i] = remaining
                    else:
                        self._entries.pop(i)
                    self._save_unlocked()
                    return {"success": True}
        return {"success": False, "error": f"No match for: {key[:50]!r}"}

    def read(self) -> str:
        with self._lock:
            if not self._entries:
                return ""
            return "\n".join(self._entries)

    def _format_for_prompt_unlocked(self) -> str:
        if not self._entries:
            return ""
        return "\n".join(f"- {e}" for e in self._entries)

    def format_for_prompt(self) -> str:
        with self._lock:
            return self._format_for_prompt_unlocked()


class ExperienceStore:
    """SQLite + FTS5 for cross-project experience."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._lock:
            with self._connect() as conn:
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

    def add(
        self,
        project: str,
        category: str,
        content: str,
        tags: str | list[str] | None = None,
    ) -> int:
        tag_str = ""
        if tags is None:
            tag_str = ""
        elif isinstance(tags, list):
            tag_str = ",".join(t.strip() for t in tags if str(t).strip())
        else:
            tag_str = tags.strip()

        now = time.time()
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO experiences (project, category, content, tags, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (project or "", category or "", content, tag_str, now),
                )
                conn.commit()
                return int(cur.lastrowid or 0)

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
            with self._connect() as conn:
                try:
                    if project is not None and str(project).strip() != "":
                        rows = conn.execute(
                            """
                            SELECT e.id, e.project, e.category, e.content, e.tags, e.created_at,
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
                            SELECT id, project, category, content, tags, created_at, 0
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
                            SELECT id, project, category, content, tags, created_at, 0
                            FROM experiences
                            WHERE content LIKE ?
                            ORDER BY created_at DESC
                            LIMIT ?
                            """,
                            (like, limit),
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

    def delete_conversation_for_session(self, session_tag: str) -> int:
        """Remove ephemeral per-session chat logs (used after /new)."""
        tag = (session_tag or "").strip()
        with self._lock:
            with self._connect() as conn:
                if tag:
                    cur = conn.execute(
                        """
                        DELETE FROM experiences
                        WHERE category = ? AND (tags = ? OR tags = '')
                        """,
                        ("conversation", tag),
                    )
                else:
                    cur = conn.execute(
                        "DELETE FROM experiences WHERE category = ?",
                        ("conversation",),
                    )
                conn.commit()
                return int(cur.rowcount or 0)

    def prune_conversation_older_than(self, max_age_days: float = 30.0) -> int:
        """Drop stale ephemeral conversation rows (personal butler hygiene)."""
        cutoff = time.time() - max(1.0, float(max_age_days)) * 86400.0
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    """
                    DELETE FROM experiences
                    WHERE category = ? AND created_at < ?
                    """,
                    ("conversation", cutoff),
                )
                conn.commit()
                return int(cur.rowcount or 0)

    def get_recent(self, limit: int = 5) -> list[dict[str, Any]]:
        with self._lock:
            with self._connect() as conn:
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


class ButlerMemory:
    """Tenant-scoped Butler memory: owner profile + cross-project experience."""

    def __init__(self, butler_home: Path, *, tenant_id: str = "default"):
        from butler.tenant import (
            DEFAULT_TENANT,
            migrate_legacy_memory_layout,
            normalize_tenant_id,
            tenant_memory_dir,
        )

        self.butler_home = Path(butler_home).expanduser().resolve()
        self.tenant_id = normalize_tenant_id(tenant_id or DEFAULT_TENANT)
        migrate_legacy_memory_layout(self.butler_home)
        mem_dir = tenant_memory_dir(self.butler_home, self.tenant_id)
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.profile = ProfileStore(mem_dir / "profile.json")
        self.experience = ExperienceStore(mem_dir / "experience.db")
        self._maybe_prune_stale_conversations()

    def _maybe_prune_stale_conversations(self) -> None:
        import os

        raw = os.getenv("BUTLER_EXPERIENCE_PRUNE_DAYS", "30").strip()
        if raw in ("0", "off", "false", "no"):
            return
        try:
            days = float(raw)
        except ValueError:
            days = 30.0
        removed = self.experience.prune_conversation_older_than(days)
        if removed:
            logger.info("Pruned %d stale conversation experience row(s)", removed)

    @classmethod
    def default(cls, *, tenant_id: str = "default") -> ButlerMemory:
        return cls(Path.home() / ".butler", tenant_id=tenant_id)

    def get_system_context(self, current_project: str = "") -> str:
        parts: list[str] = []
        profile_text = self.profile.format_for_prompt()
        if profile_text:
            parts.append(f"## Owner profile & preferences\n{profile_text}")

        recent = [
            r for r in self.experience.get_recent(limit=20)
            if (r.get("category") or "") != "conversation"
        ][:5]
        if recent:
            lines = [
                f"- [{r['project'] or 'global'}] ({r['category'] or 'general'}) {r['content']}"
                for r in recent
            ]
            parts.append("## Recent cross-project experience\n" + "\n".join(lines))

        if current_project.strip():
            relevant = [
                r
                for r in self.experience.search(
                    current_project.strip(), project=None, limit=5
                )
                if (r.get("category") or "") != "conversation"
            ]
            if relevant:
                rel_lines = [
                    f"- [{r['project']}] {r['content']}" for r in relevant
                ]
                parts.append("## Experience relevant to current project\n" + "\n".join(rel_lines))

        if not parts:
            return "(No Butler-level memory yet.)"
        return "\n\n".join(parts)
