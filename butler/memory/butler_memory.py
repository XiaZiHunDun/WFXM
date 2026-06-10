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

from butler.io.safe_load import safe_load_json

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
            # Audit R2-19: corrupt experience file used to silently
            # lose every entry on the next read. safe_load renames
            # the corrupt file for forensic retention, logs WARNING
            # with exc_info, and records the event for /诊断.
            data = safe_load_json(
                self.path, default={}, kind="memory_experience",
            )
            if not isinstance(data, dict):
                self._entries = []
                return
            entries = data.get("entries", [])
            if not isinstance(entries, list):
                self._entries = []
                return
            self._entries = [str(e).strip() for e in entries if str(e).strip()]

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
        # Hold one connection for the lifetime of the store; audit 5.1.1
        # flagged the previous behavior of opening a fresh sqlite3.connect
        # on every operation (13+ call sites) as the main performance
        # bottleneck.
        self._conn = self._open_conn()
        self._init_db()

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except Exception:
                pass

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
        # Sprint 11 SEC-11-3: 拦截 prompt-injection payload（与 ProfileStore.add 对齐）
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
            from butler.memory.retrieval_ranking import rerank_memory_hits

            return rerank_memory_hits(out)

    def delete_conversation_for_session(self, session_tag: str) -> int:
        """Remove ephemeral per-session chat logs (used after /new)."""
        tag = (session_tag or "").strip()
        with self._lock:
            conn = self._conn
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
            conn = self._conn
            cur = conn.execute(
                """
                DELETE FROM experiences
                WHERE category = ? AND created_at < ?
                """,
                ("conversation", cutoff),
            )
            conn.commit()
            return int(cur.rowcount or 0)

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
        def _row_dict(r: tuple) -> dict[str, Any]:
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
        try:
            from butler.skills.seed_bundled import ensure_bundled_tenant_skills

            ensure_bundled_tenant_skills(self.butler_home, self.tenant_id)
        except Exception as exc:
            logger.debug("Bundled skills seed skipped: %s", exc)
        mem_dir = tenant_memory_dir(self.butler_home, self.tenant_id)
        mem_dir.mkdir(parents=True, exist_ok=True)
        self.profile = ProfileStore(mem_dir / "profile.json")
        self.experience = ExperienceStore(mem_dir / "experience.db")
        self.semantic = None
        try:
            from butler.memory.semantic_config import semantic_memory_enabled
            from butler.memory.semantic_index import SemanticMemoryIndex

            if semantic_memory_enabled():
                self.semantic = SemanticMemoryIndex(mem_dir / "memory_vectors.db")
        except Exception as exc:
            logger.warning("Semantic memory index disabled: %s", exc)
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

    def close(self) -> None:
        """Release sqlite connections held by experience and semantic stores."""
        try:
            self.experience.close()
        except Exception:
            pass
        sem = self.semantic
        if sem is not None:
            try:
                sem.close()
            except Exception:
                pass

    def sync_profile_vectors(self) -> int:
        """Rebuild owner_profile rows in the vector index from profile.json."""
        sem = self.semantic
        if sem is None:
            return 0
        from butler.memory.semantic_index import SOURCE_OWNER_PROFILE

        cleared = sem.delete_source_prefix(SOURCE_OWNER_PROFILE)
        indexed = 0
        entries = list(getattr(self.profile, "_entries", []) or [])
        for idx, entry in enumerate(entries):
            text = str(entry).strip()
            if not text:
                continue
            sem.upsert(
                source=SOURCE_OWNER_PROFILE,
                source_id=f"entry:{idx}",
                content=text,
                project="",
                category="profile",
            )
            indexed += 1
        logger.debug("Profile vectors: cleared %d, indexed %d", cleared, indexed)
        return indexed

    def search_profile_vectors(self, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
        if self.semantic is None:
            return []
        return self.semantic.search_owner_profile(query, limit=limit)

    def triplet_index(self):
        if self.semantic is None:
            return None
        from butler.memory.triplets import TripletIndex

        return TripletIndex(self.semantic.db_path)
