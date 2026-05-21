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
from butler.memory.semantic_config import (
    hybrid_fts_weight,
    hybrid_vector_weight,
    semantic_search_limit,
)
logger = logging.getLogger(__name__)

_CONVERSATION = "conversation"

SOURCE_EXPERIENCE = "experience"
SOURCE_PROJECT = "project_memory"
SOURCE_OWNER_PROFILE = "owner_profile"


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
                self._ensure_vector_columns(conn)
                conn.commit()

    def _ensure_vector_columns(self, conn: sqlite3.Connection) -> None:
        cols = {row[1] for row in conn.execute("PRAGMA table_info(memory_vectors)").fetchall()}
        if "access_count" not in cols:
            conn.execute(
                "ALTER TABLE memory_vectors ADD COLUMN access_count INTEGER NOT NULL DEFAULT 0"
            )
        if "last_accessed_at" not in cols:
            conn.execute(
                "ALTER TABLE memory_vectors ADD COLUMN last_accessed_at REAL NOT NULL DEFAULT 0"
            )

    def count_rows(self) -> int:
        with self._lock:
            with self._connect() as conn:
                row = conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
                return int(row[0] if row else 0)

    def count_by_source(self, source: str) -> int:
        src = (source or "").strip()
        if not src:
            return 0
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    "SELECT COUNT(*) FROM memory_vectors WHERE source = ?",
                    (src,),
                ).fetchone()
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
                        updated_at=excluded.updated_at,
                        access_count=memory_vectors.access_count
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
                        SELECT source, source_id, project, category, content, embedding_json,
                               updated_at, access_count, last_accessed_at
                        FROM memory_vectors
                        WHERE project = ? OR project = ''
                        """,
                        (project.strip(),),
                    ).fetchall()
                else:
                    rows = conn.execute(
                        """
                        SELECT source, source_id, project, category, content, embedding_json,
                               updated_at, access_count, last_accessed_at
                        FROM memory_vectors
                        """
                    ).fetchall()
        for row in rows:
            (
                source,
                source_id,
                proj,
                cat,
                content,
                emb_json,
                updated_at,
                access_count,
                last_accessed_at,
            ) = row
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
                        "created_at": float(updated_at or 0),
                        "updated_at": float(updated_at or 0),
                        "access_count": int(access_count or 0),
                        "last_accessed_at": float(last_accessed_at or 0),
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = [item for _, item in scored[:cap]]
        self._record_access_hits(hits)
        from butler.memory.retrieval_ranking import rerank_memory_hits

        return rerank_memory_hits(hits)

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
        fts_weight = hybrid_fts_weight()

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
        self._record_access_hits(out)
        from butler.memory.retrieval_ranking import rerank_memory_hits

        return rerank_memory_hits(out)

    def _record_access_hits(self, hits: list[dict[str, Any]]) -> None:
        if not hits:
            return
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                for hit in hits:
                    src = str(hit.get("source") or "")
                    sid = str(hit.get("source_id") or "")
                    if not src or not sid:
                        continue
                    conn.execute(
                        """
                        UPDATE memory_vectors
                        SET access_count = access_count + 1, last_accessed_at = ?
                        WHERE source = ? AND source_id = ?
                        """,
                        (now, src, sid),
                    )
                conn.commit()

    def delete_source_prefix(self, source: str) -> int:
        with self._lock:
            with self._connect() as conn:
                cur = conn.execute(
                    "DELETE FROM memory_vectors WHERE source = ?",
                    (source,),
                )
                conn.commit()
                return int(cur.rowcount or 0)

    def search_owner_profile(self, query: str, *, limit: int = 4) -> list[dict[str, Any]]:
        """Vector search limited to owner profile entries."""
        q = (query or "").strip()
        if not q:
            return []
        cap = max(1, min(int(limit), 12))
        qvec = self.embedder.embed(q)
        scored: list[tuple[float, dict[str, Any]]] = []
        with self._lock:
            with self._connect() as conn:
                rows = conn.execute(
                    """
                    SELECT source_id, content, embedding_json, updated_at,
                           access_count, last_accessed_at
                    FROM memory_vectors
                    WHERE source = ?
                    """,
                    (SOURCE_OWNER_PROFILE,),
                ).fetchall()
        for source_id, content, emb_json, updated_at, access_count, last_accessed_at in rows:
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
                        "source": SOURCE_OWNER_PROFILE,
                        "source_id": source_id,
                        "project": "",
                        "category": "profile",
                        "content": content,
                        "score": sim,
                        "retrieval": "vector-profile",
                        "created_at": float(updated_at or 0),
                        "access_count": int(access_count or 0),
                    },
                )
            )
        scored.sort(key=lambda x: x[0], reverse=True)
        hits = [item for _, item in scored[:cap]]
        self._record_access_hits(hits)
        from butler.memory.retrieval_ranking import rerank_memory_hits

        return rerank_memory_hits(hits)


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
        index_triplets_for_content(
            semantic,
            content,
            project=project or "",
            source=SOURCE_EXPERIENCE,
            source_ref=str(row_id),
        )
    except Exception as exc:
        logger.warning("Semantic index upsert failed for experience %s: %s", row_id, exc)


def index_triplets_for_content(
    semantic: SemanticMemoryIndex | None,
    content: str,
    *,
    project: str = "",
    source: str = "",
    source_ref: str = "",
) -> int:
    if semantic is None:
        return 0
    from butler.memory.triplets import TripletIndex

    try:
        return TripletIndex(semantic.db_path).upsert_from_content(
            content=content,
            project=project,
            source=source,
            source_ref=source_ref,
        )
    except Exception as exc:
        logger.debug("Triplet index skipped: %s", exc)
        return 0


def hybrid_experience_search(
    semantic: SemanticMemoryIndex | None,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
    experience_store: Any | None = None,
) -> list[dict[str, Any]]:
    """FTS-only when semantic disabled; otherwise hybrid merge."""
    fts_hits = fts_search(query, project=project, limit=limit * 2)
    if semantic is None:
        out = fts_hits[:limit]
    else:
        try:
            out = semantic.hybrid_search(query, fts_hits, project=project, limit=limit)
        except Exception as exc:
            logger.warning("Hybrid search failed, using FTS: %s", exc)
            out = fts_hits[:limit]
    _record_experience_access_from_hits(experience_store, out)
    return out


def _record_experience_access_from_hits(
    experience_store: Any | None,
    hits: list[dict[str, Any]],
) -> None:
    if experience_store is None or not hits:
        return
    ids: list[int] = []
    for hit in hits:
        if (hit.get("source") or SOURCE_EXPERIENCE) not in (SOURCE_EXPERIENCE, "", None):
            continue
        raw = hit.get("id") or hit.get("source_id")
        try:
            ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    if ids and hasattr(experience_store, "record_access"):
        try:
            experience_store.record_access(ids)
        except Exception as exc:
            logger.debug("Experience access bump skipped: %s", exc)
