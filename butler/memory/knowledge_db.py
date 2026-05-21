"""Project knowledge.db — SQLite mirror of facts.json for tooling (SSOT remains JSON)."""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any


class ProjectKnowledgeDb:
    """Lightweight key-value snapshot of auto-extracted project facts."""

    def __init__(self, db_path: Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS project_facts (
                        key TEXT PRIMARY KEY,
                        value_json TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS meta (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL
                    );
                    """
                )
                conn.commit()

    def sync_from_facts(self, facts: dict[str, Any]) -> int:
        """Replace rows from a facts dict. Returns number of keys written."""
        now = time.time()
        rows = 0
        with self._lock:
            with self._connect() as conn:
                conn.execute("DELETE FROM project_facts")
                for key, val in facts.items():
                    conn.execute(
                        "INSERT INTO project_facts(key, value_json, updated_at) VALUES (?,?,?)",
                        (str(key), json.dumps(val, ensure_ascii=False), now),
                    )
                    rows += 1
                conn.execute(
                    "INSERT OR REPLACE INTO meta(key, value) VALUES (?,?)",
                    ("synced_at", str(now)),
                )
                conn.commit()
        return rows

    def count_keys(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM project_facts").fetchone()
                return int(row[0] if row else 0)

    @classmethod
    def path_for_memory_dir(cls, mem_dir: Path) -> Path:
        return Path(mem_dir) / "knowledge.db"


def sync_facts_json_to_knowledge_db(facts_json_path: Path) -> int:
    """Load facts.json and mirror into sibling knowledge.db."""
    path = Path(facts_json_path)
    if not path.is_file():
        return 0
    try:
        facts = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return 0
    if not isinstance(facts, dict):
        return 0
    db = ProjectKnowledgeDb(ProjectKnowledgeDb.path_for_memory_dir(path.parent))
    return db.sync_from_facts(facts)
