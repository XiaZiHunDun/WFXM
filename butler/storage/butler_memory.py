"""Butler-layer memory: owner profile, cross-project experience, communication prefs.

Separated from project memory because the butler layer serves a different role:
- Knows WHO the owner is (preferences, habits, identity)
- Accumulates cross-project wisdom
- Adapts communication style per channel

Storage: ~/.butler/memory/
  owner_profile.md  — bounded free-text (add/replace/remove)
  experience.db     — SQLite + FTS5 for cross-project experience
  communication.md  — channel preferences
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import tempfile
import time
from pathlib import Path

ENTRY_DELIMITER = "\n§\n"
_INJECTION_PATTERNS = re.compile(
    r"(ignore previous|system prompt|you are now|forget everything)",
    re.IGNORECASE,
)


class ProfileStore:
    """Bounded free-text store with add/replace/remove (like hackthon_alpha USER.md)."""

    def __init__(self, path: Path, char_limit: int = 2000):
        self.path = path
        self.char_limit = char_limit
        self._entries: list[str] = []
        self.load()

    def load(self) -> None:
        if self.path.exists():
            text = self.path.read_text(encoding="utf-8")
            self._entries = [e.strip() for e in text.split(ENTRY_DELIMITER) if e.strip()]
        else:
            self._entries = []

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = ENTRY_DELIMITER.join(self._entries)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                f.write(content)
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
        return sum(len(e) for e in self._entries)

    def add(self, content: str) -> dict:
        if _INJECTION_PATTERNS.search(content):
            return {"success": False, "error": "Content rejected (suspicious pattern)"}
        content = content.strip()
        if not content:
            return {"success": False, "error": "Empty content"}
        if self.total_chars + len(content) > self.char_limit:
            return {
                "success": False,
                "error": f"超出字符上限 ({self.total_chars + len(content)}/{self.char_limit})，请先删除旧内容",
            }
        self._entries.append(content)
        self.save()
        return {"success": True}

    def replace(self, old_text: str, new_content: str) -> dict:
        if _INJECTION_PATTERNS.search(new_content):
            return {"success": False, "error": "Content rejected (suspicious pattern)"}
        for i, entry in enumerate(self._entries):
            if old_text in entry:
                self._entries[i] = entry.replace(old_text, new_content)
                self.save()
                return {"success": True}
        return {"success": False, "error": f"未找到匹配的内容: {old_text[:50]}"}

    def remove(self, old_text: str) -> dict:
        for i, entry in enumerate(self._entries):
            if old_text in entry:
                remaining = entry.replace(old_text, "").strip()
                if remaining:
                    self._entries[i] = remaining
                else:
                    self._entries.pop(i)
                self.save()
                return {"success": True}
        return {"success": False, "error": f"未找到匹配的内容: {old_text[:50]}"}

    def format_for_prompt(self) -> str:
        if not self._entries:
            return ""
        return "\n".join(f"- {e}" for e in self._entries)

    @property
    def entries(self) -> list[str]:
        return list(self._entries)


class ExperienceStore:
    """SQLite + FTS5 store for cross-project experience/lessons learned."""

    def __init__(self, db_path: Path):
        self.db_path = str(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS experience (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL DEFAULT '',
                    content TEXT NOT NULL,
                    project_source TEXT NOT NULL DEFAULT '',
                    timestamp REAL NOT NULL,
                    access_count INTEGER NOT NULL DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE VIRTUAL TABLE IF NOT EXISTS experience_fts
                USING fts5(content, category, tokenize='porter unicode61')
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS exp_ai AFTER INSERT ON experience BEGIN
                    INSERT INTO experience_fts(rowid, content, category)
                    VALUES (new.id, new.content, new.category);
                END
            """)
            conn.execute("""
                CREATE TRIGGER IF NOT EXISTS exp_ad AFTER DELETE ON experience BEGIN
                    DELETE FROM experience_fts WHERE rowid = old.id;
                END
            """)

    def add(self, content: str, category: str = "", project_source: str = "") -> int:
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute(
                "INSERT INTO experience (category, content, project_source, timestamp) VALUES (?, ?, ?, ?)",
                (category, content, project_source, time.time()),
            )
            return cursor.lastrowid or 0

    def search(self, query: str, limit: int = 5) -> list[dict]:
        """Search experience by FTS5 relevance."""
        with sqlite3.connect(self.db_path) as conn:
            try:
                phrase = '"' + query.replace('"', '""') + '"'
                rows = conn.execute(
                    "SELECT e.id, e.category, e.content, e.project_source, e.timestamp, "
                    "bm25(experience_fts) AS rank "
                    "FROM experience e "
                    "JOIN experience_fts ON experience_fts.rowid = e.id "
                    "WHERE experience_fts MATCH ? "
                    "ORDER BY rank "
                    "LIMIT ?",
                    (phrase, limit),
                ).fetchall()
            except sqlite3.OperationalError:
                rows = conn.execute(
                    "SELECT id, category, content, project_source, timestamp, 0 "
                    "FROM experience WHERE content LIKE ? ORDER BY timestamp DESC LIMIT ?",
                    (f"%{query}%", limit),
                ).fetchall()

            for row in rows:
                conn.execute(
                    "UPDATE experience SET access_count = access_count + 1 WHERE id = ?",
                    (row[0],),
                )

            return [
                {
                    "id": r[0], "category": r[1], "content": r[2],
                    "project_source": r[3], "timestamp": r[4],
                }
                for r in rows
            ]

    def get_recent(self, limit: int = 10) -> list[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, category, content, project_source, timestamp "
                "FROM experience ORDER BY timestamp DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [
            {"id": r[0], "category": r[1], "content": r[2], "project_source": r[3], "timestamp": r[4]}
            for r in rows
        ]

    def count(self) -> int:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute("SELECT COUNT(*) FROM experience").fetchone()
        return row[0] if row else 0


class ButlerMemory:
    """Butler-layer memory: knows the owner, accumulates cross-project wisdom."""

    def __init__(self, butler_home: Path):
        mem_dir = butler_home / "memory"
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.profile = ProfileStore(mem_dir / "owner_profile.md", char_limit=2000)
        self.experience = ExperienceStore(mem_dir / "experience.db")
        self.comm_prefs = ProfileStore(mem_dir / "communication.md", char_limit=500)

    @classmethod
    def default(cls) -> ButlerMemory:
        from butler.config.settings import settings
        return cls(settings.butler_home)

    def get_system_context(self, current_project: str = "") -> str:
        """Build memory block for butler system prompt."""
        parts: list[str] = []

        profile_text = self.profile.format_for_prompt()
        if profile_text:
            parts.append(f"## 主公画像\n{profile_text}")

        comm_text = self.comm_prefs.format_for_prompt()
        if comm_text:
            parts.append(f"## 沟通偏好\n{comm_text}")

        if current_project:
            relevant = self.experience.search(current_project, limit=3)
            if relevant:
                exp_lines = [f"- [{e['project_source']}] {e['content']}" for e in relevant]
                parts.append(f"## 相关经验\n" + "\n".join(exp_lines))

        if not parts:
            return "(暂无管家层记忆)"
        return "\n\n".join(parts)

    def add_profile(self, content: str) -> dict:
        return self.profile.add(content)

    def replace_profile(self, old_text: str, new_content: str) -> dict:
        return self.profile.replace(old_text, new_content)

    def remove_profile(self, old_text: str) -> dict:
        return self.profile.remove(old_text)

    def add_experience(self, content: str, category: str = "", project: str = "") -> None:
        self.experience.add(content, category=category, project_source=project)

    def search_experience(self, query: str, limit: int = 5) -> list[dict]:
        return self.experience.search(query, limit=limit)
