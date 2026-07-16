"""ExperienceStore — SQLite persistence for the experience tree.

Schema: domains → categories → nodes (leaf/branch) + cross-links.
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from butler.memory.experience.taxonomy import DOMAINS, CATEGORIES

logger = logging.getLogger(__name__)


@dataclass
class ExperienceNode:
    node_id: str
    domain: str
    category: str
    name: str
    node_type: str = "leaf"  # leaf | branch
    content: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    embedding_id: str = ""
    kg_entity_id: str = ""
    hit_count: int = 0
    success_count: int = 0
    fail_count: int = 0
    last_used: float = 0.0
    created_at: float = 0.0
    updated_at: float = 0.0

    @property
    def success_rate(self) -> float:
        total = self.success_count + self.fail_count
        if total == 0:
            return 0.0
        return self.success_count / total

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id": self.node_id,
            "domain": self.domain,
            "category": self.category,
            "name": self.name,
            "node_type": self.node_type,
            "content": self.content,
            "metadata": self.metadata,
            "embedding_id": self.embedding_id,
            "kg_entity_id": self.kg_entity_id,
            "hit_count": self.hit_count,
            "success_count": self.success_count,
            "fail_count": self.fail_count,
            "last_used": self.last_used,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "success_rate": self.success_rate,
        }


@dataclass
class ExperienceHit:
    """A retrieved experience with relevance score."""
    node: ExperienceNode
    score: float
    source: str  # sqlite | chromadb | knowledge_graph


class ExperienceStore:
    _SCHEMA_VERSION = 2

    def __init__(self, db_path: str | None = None):
        project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
        default_data_dir = os.path.join(project_root, ".wfxm_data")

        self._db_path = db_path or os.path.join(
            default_data_dir, "experience_tree.db"
        )
        self._lock = threading.RLock()
        self._ensure_schema()
        self._seed_taxonomy()

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
                        CREATE TABLE experience_domains (
                            domain_id TEXT PRIMARY KEY,
                            name TEXT NOT NULL,
                            description TEXT,
                            keywords TEXT,
                            hit_count INTEGER DEFAULT 0,
                            created_at REAL NOT NULL
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE experience_categories (
                            category_id TEXT NOT NULL,
                            domain_id TEXT NOT NULL,
                            name TEXT NOT NULL,
                            description TEXT,
                            backend TEXT,
                            created_at REAL NOT NULL,
                            PRIMARY KEY (category_id, domain_id)
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE experience_nodes (
                            node_id TEXT PRIMARY KEY,
                            domain_id TEXT NOT NULL,
                            category_id TEXT NOT NULL,
                            name TEXT NOT NULL,
                            node_type TEXT DEFAULT 'leaf',
                            content TEXT,
                            metadata_json TEXT DEFAULT '{}',
                            embedding_id TEXT,
                            kg_entity_id TEXT,
                            hit_count INTEGER DEFAULT 0,
                            success_count INTEGER DEFAULT 0,
                            fail_count INTEGER DEFAULT 0,
                            last_used REAL DEFAULT 0,
                            created_at REAL NOT NULL,
                            updated_at REAL NOT NULL
                        )
                    """)
                    conn.execute("""
                        CREATE TABLE experience_links (
                            source_node_id TEXT NOT NULL,
                            target_node_id TEXT NOT NULL,
                            relation TEXT NOT NULL,
                            weight REAL DEFAULT 1.0,
                            PRIMARY KEY (source_node_id, target_node_id, relation)
                        )
                    """)
                    conn.execute("CREATE INDEX idx_nodes_domain ON experience_nodes(domain_id)")
                    conn.execute("CREATE INDEX idx_nodes_category ON experience_nodes(category_id)")
                    conn.execute("CREATE INDEX idx_nodes_hit ON experience_nodes(hit_count DESC)")
                    conn.execute("CREATE INDEX idx_nodes_last_used ON experience_nodes(last_used DESC)")

                    conn.execute("""
                        CREATE VIRTUAL TABLE experience_nodes_fts USING fts5(
                            node_id, name, content, 
                        )
                    """)

                    version = 1

                if version == 1:
                    conn.execute("DROP TABLE IF EXISTS experience_nodes_fts")
                    conn.execute("""
                        CREATE VIRTUAL TABLE experience_nodes_fts USING fts5(
                            node_id, name, content
                        )
                    """)
                    cursor = conn.execute("SELECT node_id, name, content FROM experience_nodes")
                    rows = cursor.fetchall()
                    for row in rows:
                        conn.execute("INSERT INTO experience_nodes_fts(node_id, name, content) VALUES (?, ?, ?)", row)
                    version = 2
                conn.execute(f"PRAGMA user_version = {self._SCHEMA_VERSION}")
                conn.commit()

    def _seed_taxonomy(self) -> None:
        now = time.time()
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                for did, d in DOMAINS.items():
                    conn.execute("""
                        INSERT OR IGNORE INTO experience_domains
                        (domain_id, name, description, keywords, hit_count, created_at)
                        VALUES (?, ?, ?, ?, 0, ?)
                    """, (did, d["name"], d["description"],
                          json.dumps(d["keywords"], ensure_ascii=False), now))

                    for cid, c in CATEGORIES.items():
                        conn.execute("""
                            INSERT OR IGNORE INTO experience_categories
                            (category_id, domain_id, name, description, backend, created_at)
                            VALUES (?, ?, ?, ?, ?, ?)
                        """, (cid, did, c["name"], c["description"], c["backend"], now))

                conn.commit()

    def save_node(self, node: ExperienceNode) -> None:
        now = time.time()
        if not node.created_at:
            node.created_at = now
        node.updated_at = now

        node_id = node.node_id or f"{node.domain}/{node.category}/{node.name}"

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO experience_nodes
                    (node_id, domain_id, category_id, name, node_type, content,
                     metadata_json, embedding_id, kg_entity_id,
                     hit_count, success_count, fail_count, last_used,
                     created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node_id, node.domain, node.category, node.name,
                    node.node_type, node.content,
                    json.dumps(node.metadata, ensure_ascii=False),
                    node.embedding_id, node.kg_entity_id,
                    node.hit_count, node.success_count, node.fail_count,
                    node.last_used, node.created_at, node.updated_at,
                ))

                conn.execute("""
                    INSERT OR REPLACE INTO experience_nodes_fts(node_id, name, content)
                    VALUES (?, ?, ?)
                """, (node_id, node.name, node.content))

                conn.commit()

        node.node_id = node_id

    def get_node(self, node_id: str) -> Optional[ExperienceNode]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("""
                    SELECT node_id, domain_id, category_id, name, node_type, content,
                           metadata_json, embedding_id, kg_entity_id,
                           hit_count, success_count, fail_count, last_used,
                           created_at, updated_at
                    FROM experience_nodes WHERE node_id = ?
                """, (node_id,))
                row = cursor.fetchone()

        if not row:
            return None
        return self._row_to_node(row)

    def search_by_domain(
        self,
        domain_id: str,
        query: str = "",
        category_id: str = "",
        limit: int = 10,
    ) -> list[ExperienceNode]:
        sql = """
            SELECT node_id, domain_id, category_id, name, node_type, content,
                   metadata_json, embedding_id, kg_entity_id,
                   hit_count, success_count, fail_count, last_used,
                   created_at, updated_at
            FROM experience_nodes WHERE domain_id = ?
        """
        params: list[Any] = [domain_id]

        if category_id:
            sql += " AND category_id = ?"
            params.append(category_id)

        if query:
            sql += """ AND node_id IN (
                SELECT node_id FROM experience_nodes_fts
                WHERE experience_nodes_fts MATCH ?
            )"""
            params.append(query)

        sql += " ORDER BY hit_count DESC, last_used DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()

        return [self._row_to_node(r) for r in rows]

    def search_fts(self, query: str, limit: int = 10) -> list[ExperienceNode]:
        if not query.strip():
            return []
        fts_query = " OR ".join(query.split())
        sql = """
            SELECT n.node_id, n.domain_id, n.category_id, n.name, n.node_type, n.content,
                   n.metadata_json, n.embedding_id, n.kg_entity_id,
                   n.hit_count, n.success_count, n.fail_count, n.last_used,
                   n.created_at, n.updated_at
            FROM experience_nodes n
            JOIN experience_nodes_fts ON n.node_id = experience_nodes_fts.node_id
            WHERE experience_nodes_fts MATCH ?
            ORDER BY n.hit_count DESC, n.last_used DESC
            LIMIT ?
        """
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                try:
                    cursor = conn.execute(sql, (fts_query, limit))
                    rows = cursor.fetchall()
                except (sqlite3.OperationalError, sqlite3.DatabaseError) as e:
                    logger.warning("FTS5 query failed: %s", e)
                    self._schedule_fts_rebuild()
                    return []

        return [self._row_to_node(r) for r in rows]

    def _schedule_fts_rebuild(self) -> None:
        """Schedule FTS5 index rebuild in a background thread."""
        import threading
        t = threading.Thread(
            target=self.rebuild_fts_index,
            daemon=True,
            name="FTS5Rebuild",
        )
        t.start()
        logger.info("FTS5 rebuild scheduled in background thread")

    def increment_hit(self, node_id: str, success: bool = True) -> None:
        now = time.time()
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                if success:
                    conn.execute("""
                        UPDATE experience_nodes
                        SET hit_count = hit_count + 1, success_count = success_count + 1,
                            last_used = ?, updated_at = ?
                        WHERE node_id = ?
                    """, (now, now, node_id))
                else:
                    conn.execute("""
                        UPDATE experience_nodes
                        SET hit_count = hit_count + 1, fail_count = fail_count + 1,
                            last_used = ?, updated_at = ?
                        WHERE node_id = ?
                    """, (now, now, node_id))

                conn.execute("""
                    UPDATE experience_domains
                    SET hit_count = hit_count + 1
                    WHERE domain_id = (
                        SELECT domain_id FROM experience_nodes WHERE node_id = ?
                    )
                """, (node_id,))
                conn.commit()

    def add_link(self, source_id: str, target_id: str, relation: str, weight: float = 1.0) -> None:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("""
                    INSERT OR REPLACE INTO experience_links
                    (source_node_id, target_node_id, relation, weight)
                    VALUES (?, ?, ?, ?)
                """, (source_id, target_id, relation, weight))
                conn.commit()

    def rebuild_fts_index(self) -> None:
        """Rebuild the FTS5 index when it becomes corrupted."""
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                conn.execute("DROP TABLE IF EXISTS experience_nodes_fts")
                conn.execute("""
                    CREATE VIRTUAL TABLE experience_nodes_fts USING fts5(
                        node_id, name, content, 
                    )
                """)
                cursor = conn.execute("SELECT node_id, name, content FROM experience_nodes")
                rows = cursor.fetchall()
                for row in rows:
                    conn.execute("""
                        INSERT INTO experience_nodes_fts(node_id, name, content)
                        VALUES (?, ?, ?)
                    """, row)
                conn.commit()
                logger.info("FTS5 index rebuilt with %d documents", len(rows))

    def get_linked_nodes(self, node_id: str, relation: str = "") -> list[str]:
        sql = "SELECT target_node_id FROM experience_links WHERE source_node_id = ?"
        params: list[Any] = [node_id]
        if relation:
            sql += " AND relation = ?"
            params.append(relation)
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(sql, params)
                return [r[0] for r in cursor.fetchall()]

    def get_domain_stats(self, domain_id: str) -> dict[str, Any]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("""
                    SELECT COUNT(*), SUM(hit_count), SUM(success_count)
                    FROM experience_nodes WHERE domain_id = ?
                """, (domain_id,))
                total, hits, successes = cursor.fetchone()

                cursor = conn.execute("""
                    SELECT hit_count FROM experience_domains WHERE domain_id = ?
                """, (domain_id,))
                domain_hits = cursor.fetchone()[0] or 0

        return {
            "domain_id": domain_id,
            "total_nodes": total or 0,
            "total_hits": hits or 0,
            "total_successes": successes or 0,
            "domain_hits": domain_hits,
        }

    def get_all_stats(self) -> dict[str, Any]:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM experience_nodes")
                total_nodes = cursor.fetchone()[0]
                cursor = conn.execute("SELECT COUNT(*) FROM experience_links")
                total_links = cursor.fetchone()[0]

                domain_stats = {}
                for did in DOMAINS:
                    cursor = conn.execute("""
                        SELECT COUNT(*), COALESCE(SUM(hit_count), 0)
                        FROM experience_nodes WHERE domain_id = ?
                    """, (did,))
                    count, hits = cursor.fetchone()
                    domain_stats[did] = {"nodes": count, "hits": hits}

        return {
            "total_nodes": total_nodes,
            "total_links": total_links,
            "domain_stats": domain_stats,
            "db_path": self._db_path,
        }

    def list_nodes(self, domain_id: str = "", category_id: str = "", limit: int = 50) -> list[ExperienceNode]:
        sql = """
            SELECT node_id, domain_id, category_id, name, node_type, content,
                   metadata_json, embedding_id, kg_entity_id,
                   hit_count, success_count, fail_count, last_used,
                   created_at, updated_at
            FROM experience_nodes WHERE 1=1
        """
        params: list[Any] = []
        if domain_id:
            sql += " AND domain_id = ?"
            params.append(domain_id)
        if category_id:
            sql += " AND category_id = ?"
            params.append(category_id)
        sql += " ORDER BY last_used DESC LIMIT ?"
        params.append(limit)

        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute(sql, params)
                rows = cursor.fetchall()

        return [self._row_to_node(r) for r in rows]

    def delete_node(self, node_id: str) -> bool:
        with self._lock:
            with sqlite3.connect(self._db_path) as conn:
                cursor = conn.execute("DELETE FROM experience_nodes WHERE node_id = ?", (node_id,))
                conn.execute("DELETE FROM experience_nodes_fts WHERE node_id = ?", (node_id,))
                conn.execute("DELETE FROM experience_links WHERE source_node_id = ? OR target_node_id = ?", (node_id, node_id))
                conn.commit()
                return cursor.rowcount > 0

    def _row_to_node(self, row: tuple) -> ExperienceNode:
        try:
            metadata = json.loads(row[6]) if row[6] else {}
        except json.JSONDecodeError:
            metadata = {}
        return ExperienceNode(
            node_id=row[0], domain=row[1], category=row[2], name=row[3],
            node_type=row[4], content=row[5] or "", metadata=metadata,
            embedding_id=row[7] or "", kg_entity_id=row[8] or "",
            hit_count=row[9], success_count=row[10], fail_count=row[11],
            last_used=row[12], created_at=row[13], updated_at=row[14],
        )


_singleton: Optional[ExperienceStore] = None


def get_experience_store() -> ExperienceStore:
    global _singleton
    if _singleton is None:
        _singleton = ExperienceStore()
    return _singleton
