"""Local vector semantic index (derivative of MEMORY / experience rows)."""

from __future__ import annotations

import json
import logging
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable

from butler.memory.embedding import Embedder, cosine_similarity, get_embedder
from butler.memory.semantic_config import hybrid_vector_weight, semantic_search_limit
logger = logging.getLogger(__name__)

_CONVERSATION = "conversation"

SOURCE_EXPERIENCE = "experience"
SOURCE_PROJECT = "project_memory"


class SemanticMemoryIndex:
    """SQLite-backed embedding index with hybrid FTS merge."""

    def __init__(self, db_path: Path, embedder: Embedder | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
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
                    CREATE TABLE IF NOT EXISTS memory_vectors (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        source TEXT NOT NULL,
                        source_id TEXT NOT NULL,
                        project TEXT NOT NULL DEFAULT '',
                        category TEXT NOT NULL DEFAULT '',
                        content TEXT NOT NULL,
                        embedding_json TEXT NOT NULL,
                        model_id TEXT NOT NULL,
                        updated_at REAL NOT NULL,
                        UNIQUE(source, source_id)
                    );
                    CREATE INDEX IF NOT EXISTS idx_mv_project ON memory_vectors(project);
                    CREATE INDEX IF NOT EXISTS idx_mv_source ON memory_vectors(source);
                    """
                )
                conn.commit()

    def count_rows(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
                return int(row[0] if row else 0)

    @property
    def model_id(self) -> str:
        return self.embedder.model_id

    def upsert(
        self,
        *,
        source: str,
        source_id: str,
        content: str,
        project: str = "",
        category: str = "",
    ) -> None:
        text = (content or "").strip()
        if not text or (category or "") == _CONVERSATION:
            return
        vec = self.embedder.embed(text)
        payload = json.dumps(vec, ensure_ascii=False)
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO memory_vectors (
                        source, source_id, project, category, content,
                        embedding_json, model_id, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(source, source_id) DO UPDATE SET
                        project=excluded.project,
                        category=excluded.category,
                        content=excluded.content,
                        embedding_json=excluded.embedding_json,
                        model_id=excluded.model_id,
                        updated_at=excluded.updated_at
                    """,
                    (
                        source,
                        str(source_id),
                        project or "",
                        category or "",
                        text,
                        payload,
                        self.embedder.model_id,
                        now,
                    ),
                )
                conn.commit()

    def delete(self, source: str, source_id: str) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    "DELETE FROM memory_vectors WHERE source = ? AND source_id = ?",
                    (source, str(source_id)),
                )
                conn.commit()

    def search(self, query: str, *, project: str | None = None, limit: int | None = None) -> list[dict[str, Any]]:
        """Pure vector search ranked by cosine similarity."""
        q = (query or "").strip()
        if not q:
            return []
        cap = limit if limit is not None else semantic_search_limit()
        qvec = self.embedder.embed(q)
        scored: list[tuple[float, dict[str, Any]]] = []
        with self._lock:
            with self._connect() as conn:
                if project is not None and str(project).strip():
                    rows = conn.execute(
                        """
                        SELECT source, source_id, project, category, content, embedding_json
                        FROM memory_vectors
                        WHERE project = ? OR project = ''
                        """,
                        (project.strip(),),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT source, source_id, project, category, content, embedding_json
                        FROM memory_vectors
                        """
                    ).fetchall()
        for source, source_id, proj, cat, content, emb_json in rows:
            try:
                vec = json.loads(emb_json)
            except json.JSONDecodeError:
                continue
            sim = cosine_similarity(qvec, vec)
            if sim <= 0.05:
                continue
            scored.append(
                (
                    sim,
                    {
                        "source": source,
                        "source_id": source_id,
                        "project": proj,
                        "category": cat,
                        "content": content,
                        "score": sim,
                        "retrieval": "vector",
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:cap]]

    def hybrid_search(
        self,
        query: str,
        fts_hits: list[dict[str, Any]],
        *,
        project: str | None = None,
        limit: int | None = None,
    ) -> list[dict[str, Any]]:
        """Merge vector top-K with FTS hits (RRF-style), dedupe by content."""
        cap = limit if limit is not None else semantic_search_limit()
        vec_weight = hybrid_vector_weight()
        fts_weight = 1.0 - vec_weight

        vec_hits = self.search(query, project=project, limit=cap * 2)
        scores: dict[str, float] = {}
        rows: dict[str, dict[str, Any]] = {}

        for rank, hit in enumerate(vec_hits):
            key = _hit_key(hit)
            scores[key] = scores.get(key, 0.0) + vec_weight / (60 + rank + 1)
            rows[key] = {**hit, "retrieval": "hybrid-vector"}

        for rank, hit in enumerate(fts_hits):
            if (hit.get("category") or "") == _CONVERSATION:
                continue
            key = _hit_key(hit)
            scores[key] = scores.get(key, 0.0) + fts_weight / (60 + rank + 1)
            merged = dict(hit)
            merged["retrieval"] = merged.get("retrieval") or "hybrid-fts"
            rows[key] = merged

        ordered = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        out: list[dict[str, Any]] = []
        for key, score in ordered[:cap]:
            item = dict(rows[key])
            item["score"] = round(score, 6)
            out.append(item)
        return out


def _hit_key(hit: dict[str, Any]) -> str:
    sid = hit.get("source_id") or hit.get("id")
    if sid is not None:
        return f"{hit.get('source', SOURCE_EXPERIENCE)}:{sid}"
    content = str(hit.get("content") or "").strip()
    return f"content:{hash(content) & 0xFFFFFFFF:08x}"


def index_experience_row(
    semantic: SemanticMemoryIndex | None,
    row_id: int,
    *,
    project: str,
    category: str,
    content: str,
) -> None:
    if semantic is None or not content.strip():
        return
    if (category or "") == _CONVERSATION:
        return
    try:
        semantic.upsert(
            source=SOURCE_EXPERIENCE,
            source_id=str(row_id),
            content=content,
            project=project or "",
            category=category or "",
        )
    except Exception as exc:
        logger.warning("Semantic index upsert failed for experience %s: %s", row_id, exc)


def hybrid_experience_search(
    semantic: SemanticMemoryIndex | None,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
) -> list[dict[str, Any]]:
    """FTS-only when semantic disabled; otherwise hybrid merge."""
    fts_hits = fts_search(query, project=project, limit=limit * 2)
    if semantic is None:
        return fts_hits[:limit]
    try:
        return semantic.hybrid_search(query, fts_hits, project=project, limit=limit)
    except Exception as exc:
        logger.warning("Hybrid search failed, using FTS: %s", exc)
        return fts_hits[:limit]
