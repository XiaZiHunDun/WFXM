"""KnowledgeWarehouse — material storage with state machine.

Material status flow:
    raw → queued → digesting → digested → archived
               ↘ failed ↗
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class Material:
    """A knowledge material to be digested."""

    material_id: str
    domain_hint: str              # User-provided domain hint
    source_type: str              # text | url | file
    raw_content: str              # Text content
    content_hash: str             # SHA-256 hash for deduplication
    status: str                   # raw | queued | digesting | digested | failed | archived
    title: str = ""
    source_url: str = ""
    source_file: str = ""
    digested_experience_ids: list[str] = field(default_factory=list)
    error_msg: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    priority: int = 0             # 0=low, 1=medium, 2=high
    created_at: float = 0.0
    updated_at: float = 0.0
    digested_at: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "material_id": self.material_id,
            "domain_hint": self.domain_hint,
            "source_type": self.source_type,
            "title": self.title,
            "source_url": self.source_url,
            "source_file": self.source_file,
            "content_hash": self.content_hash,
            "status": self.status,
            "digested_experience_ids": self.digested_experience_ids,
            "error_msg": self.error_msg,
            "metadata": self.metadata,
            "priority": self.priority,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "digested_at": self.digested_at,
        }


class KnowledgeWarehouse:
    _SCHEMA_VERSION = 1

    STATUS_RAW = "raw"
    STATUS_QUEUED = "queued"
    STATUS_DIGESTING = "digesting"
    STATUS_DIGESTED = "digested"
    STATUS_FAILED = "failed"
    STATUS_ARCHIVED = "archived"

    ALL_STATUSES = [STATUS_RAW, STATUS_QUEUED, STATUS_DIGESTING, STATUS_DIGESTED, STATUS_FAILED, STATUS_ARCHIVED]

    def __init__(self, db_path: str | None = None, storage_dir: str | None = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        default_data_dir = os.path.join(project_root, ".wfxm_data")

        self._db_path = db_path or os.path.join(
            default_data_dir, "knowledge_warehouse.db"
        )
        self._storage_dir = storage_dir or os.path.join(
            default_data_dir, "knowledge_warehouse"
        )
        os.makedirs(self._storage_dir, exist_ok=True)
        os.makedirs(os.path.join(self._storage_dir, "files"), exist_ok=True)
        os.makedirs(os.path.join(self._storage_dir, "archived"), exist_ok=True)

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
                        CREATE TABLE materials (
                            material_id TEXT PRIMARY KEY,
                            domain_hint TEXT NOT NULL,
                            source_type TEXT NOT NULL,
                            title TEXT DEFAULT '',
                            source_url TEXT DEFAULT '',
                            source_file TEXT DEFAULT '',
                            content_hash TEXT NOT NULL UNIQUE,
                            raw_content TEXT,
                            status TEXT DEFAULT 'raw',
                            digested_experience_ids TEXT DEFAULT '[]',
                            error_msg TEXT DEFAULT '',
                            metadata_json TEXT DEFAULT '{}',
                            priority INTEGER DEFAULT 0,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL,
                            digested_at REAL DEFAULT 0
                        )
                    """)
                    conn.execute("CREATE INDEX idx_materials_status ON materials(status)")
                    conn.execute("CREATE INDEX idx_materials_domain ON materials(domain_hint)")
                    conn.execute("CREATE INDEX idx_materials_priority ON materials(priority DESC)")
                    conn.execute("CREATE INDEX idx_materials_created ON materials(created_at DESC)")

                    conn.execute("""
                        CREATE TABLE material_tags (
                            material_id TEXT NOT NULL,
                            tag TEXT NOT NULL,
                            PRIMARY KEY (material_id, tag)
                        )
                    """)

                    version = 1

                conn.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
                conn.commit()

    def add_material(
        self,
        domain_hint: str,
        raw_content: str,
        source_type: str = "text",
        title: str = "",
        source_url: str = "",
        source_file: str = "",
        metadata: dict[str, Any] | None = None,
        priority: int = 0,
    ) -> tuple[str, bool]:
        """Add a material. Returns (material_id, was_added).

        was_added is False if material already exists (deduplication).
        """
        content_hash = self._compute_hash(raw_content)
        material_id = f"mat_{content_hash[:16]}_{int(time.time())}"

        now = time.time()

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT material_id FROM materials WHERE content_hash = ?",
                    (content_hash,),
                )
                existing = cursor.fetchone()
                if existing:
                    return existing[0], False

                conn.execute("""
                    INSERT INTO materials
                    (material_id, domain_hint, source_type, title, source_url, source_file,
                     content_hash, raw_content, status, metadata_json, priority,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'raw', ?, ?, ?, ?)
                """, (
                    material_id, domain_hint, source_type, title, source_url, source_file,
                    content_hash, raw_content, json.dumps(metadata or {}, ensure_ascii=False),
                    priority, now, now,
                ))
                conn.commit()

        return material_id, True

    def get_material(self, material_id: str) -> Optional[Material]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("""
                    SELECT material_id, domain_hint, source_type, title, source_url, source_file,
                           content_hash, raw_content, status, digested_experience_ids,
                           error_msg, metadata_json, priority, created_at, updated_at, digested_at
                    FROM materials WHERE material_id = ?
                """, (material_id,))
                row = cursor.fetchone()

        if not row:
            return None
        return self._row_to_material(row)

    def list_materials(
        self,
        status: str = "",
        domain_hint: str = "",
        limit: int = 50,
        offset: int = 0,
    ) -> list[Material]:
        sql = """
            SELECT material_id, domain_hint, source_type, title, source_url, source_file,
                   content_hash, raw_content, status, digested_experience_ids,
                   error_msg, metadata_json, priority, created_at, updated_at, digested_at
            FROM materials WHERE 1=1
        """
        params: list[Any] = []

        if status:
            sql += " AND status = ?"
            params.append(status)
        if domain_hint:
            sql += " AND domain_hint = ?"
            params.append(domain_hint)

        sql += " ORDER BY priority DESC, created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()

        return [self._row_to_material(r) for r in rows]

    def update_status(self, material_id: str, status: str, error_msg: str = "") -> None:
        now = time.time()
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    UPDATE materials
                    SET status = ?, error_msg = ?, updated_at = ?,
                        digested_at = CASE WHEN ? = 'digested' THEN ? ELSE digested_at END
                    WHERE material_id = ?
                """, (status, error_msg, now, status, now, material_id))
                conn.commit()

    def mark_digested(self, material_id: str, experience_ids: list[str]) -> None:
        now = time.time()
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    UPDATE materials
                    SET status = 'digested', digested_experience_ids = ?,
                        updated_at = ?, digested_at = ?
                    WHERE material_id = ?
                """, (json.dumps(experience_ids, ensure_ascii=False), now, now, material_id))
                conn.commit()

    def enqueue_for_digestion(self, material_id: str) -> None:
        self.update_status(material_id, self.STATUS_QUEUED)

    def get_queued_materials(self, limit: int = 10) -> list[Material]:
        return self.list_materials(status=self.STATUS_QUEUED, limit=limit)

    def get_pending_materials(self, limit: int = 10) -> list[Material]:
        sql = """
            SELECT material_id, domain_hint, source_type, title, source_url, source_file,
                   content_hash, raw_content, status, digested_experience_ids,
                   error_msg, metadata_json, priority, created_at, updated_at, digested_at
            FROM materials WHERE status IN ('raw', 'queued')
            ORDER BY priority DESC, created_at DESC LIMIT ?
        """
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(sql, (limit,))
                rows = cursor.fetchall()

        return [self._row_to_material(r) for r in rows]

    def add_tag(self, material_id: str, tag: str) -> None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT OR IGNORE INTO material_tags (material_id, tag) VALUES (?, ?)
                """, (material_id, tag))
                conn.commit()

    def get_tags(self, material_id: str) -> list[str]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(
                    "SELECT tag FROM material_tags WHERE material_id = ?",
                    (material_id,),
                )
                return [r[0] for r in cursor.fetchall()]

    def delete_material(self, material_id: str) -> bool:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("DELETE FROM materials WHERE material_id = ?", (material_id,))
                conn.execute("DELETE FROM material_tags WHERE material_id = ?", (material_id,))
                conn.commit()
                return cursor.rowcount > 0

    def get_stats(self) -> dict[str, Any]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM materials")
                total = cursor.fetchone()[0]

                status_counts = {}
                for status in self.ALL_STATUSES:
                    cursor.execute("SELECT COUNT(*) FROM materials WHERE status = ?", (status,))
                    status_counts[status] = cursor.fetchone()[0]

                domain_counts = {}
                cursor.execute("SELECT domain_hint, COUNT(*) FROM materials GROUP BY domain_hint")
                for row in cursor.fetchall():
                    domain_counts[row[0]] = row[1]

        return {
            "total_materials": total,
            "status_counts": status_counts,
            "domain_counts": domain_counts,
            "db_path": self._db_path,
            "storage_dir": self._storage_dir,
        }

    def archive_material(self, material_id: str) -> None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    UPDATE materials SET status = 'archived', updated_at = ?
                    WHERE material_id = ?
                """, (time.time(), material_id))
                conn.commit()

    def requeue_failed(self) -> int:
        """Requeue all failed materials. Returns count."""
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("""
                    UPDATE materials SET status = 'queued', error_msg = ''
                    WHERE status = 'failed'
                """)
                conn.commit()
                return cursor.rowcount

    def _compute_hash(self, content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _update_source_file(self, material_id: str, new_source_file: str) -> None:
        """Update the source_file path for a material."""
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute(
                    "UPDATE materials SET source_file = ?, updated_at = ? WHERE material_id = ?",
                    (new_source_file, time.time(), material_id)
                )
                conn.commit()

    def _row_to_material(self, row: tuple) -> Material:
        try:
            experience_ids = json.loads(row[9]) if row[9] else []
        except json.JSONDecodeError:
            experience_ids = []
        try:
            metadata = json.loads(row[11]) if row[11] else {}
        except json.JSONDecodeError:
            metadata = {}

        return Material(
            material_id=row[0],
            domain_hint=row[1],
            source_type=row[2],
            title=row[3] or "",
            source_url=row[4] or "",
            source_file=row[5] or "",
            content_hash=row[6],
            raw_content=row[7] or "",
            status=row[8],
            digested_experience_ids=experience_ids,
            error_msg=row[10] or "",
            metadata=metadata,
            priority=row[12],
            created_at=row[13],
            updated_at=row[14],
            digested_at=row[15],
        )


_singleton: Optional[KnowledgeWarehouse] = None


def get_knowledge_warehouse() -> KnowledgeWarehouse:
    global _singleton
    if _singleton is None:
        _singleton = KnowledgeWarehouse()
    return _singleton
