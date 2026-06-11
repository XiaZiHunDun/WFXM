"""Local vector semantic index (derivative of MEMORY / experience rows)."""

from __future__ import annotations

import atexit
import json
import logging
import sqlite3
import threading
import time
import weakref
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

_ACTIVE_INDICES: weakref.WeakSet[SemanticMemoryIndex] = weakref.WeakSet()
_atexit_registered = False


def close_all_semantic_indices() -> None:
    """Close every live ``SemanticMemoryIndex`` (atexit / gateway shutdown)."""
    for index in list(_ACTIVE_INDICES):
        try:
            index.close()
        except Exception as exc:
            logger.debug("semantic_index shutdown close skipped: %s", exc)


def _register_semantic_index(index: SemanticMemoryIndex) -> None:
    global _atexit_registered
    _ACTIVE_INDICES.add(index)
    if not _atexit_registered:
        atexit.register(close_all_semantic_indices)
        _atexit_registered = True


class SemanticMemoryIndex:
    """SQLite-backed embedding index with hybrid FTS merge."""

    def __init__(self, db_path: Path, embedder: Embedder | None = None) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.embedder = embedder or get_embedder()
        # Sprint 11 PERF-11-5: 拆分读写。read 不持进程级锁（依赖 sqlite3
        # Connection 内部 mutex + check_same_thread=False），write 串行
        # 化避免 DML race。原 _lock = RLock 串行化 9 处方法是性能瓶颈。
        self._write_lock = threading.Lock()
        # 向后兼容：旧测试/外部代码可能直接访问 idx._lock
        self._lock = self._write_lock
        self._conn = self._open_conn()
        self._init_schema()
        _register_semantic_index(self)

    def _open_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def close(self) -> None:
        with self._write_lock:
            conn = self._conn
            if conn is None:
                return
            try:
                conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

    def _init_schema(self) -> None:
        with self._write_lock:
            conn = self._conn
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
        # Sprint 11 PERF-11-5: read 不持锁（依赖 sqlite3 Connection 内部 mutex）
        conn = self._conn
        row = conn.execute("SELECT COUNT(*) FROM memory_vectors").fetchone()
        return int(row[0] if row else 0)

    def count_by_source(self, source: str) -> int:
        src = (source or "").strip()
        if not src:
            return 0
        # Sprint 11 PERF-11-5: read 不持锁
        conn = self._conn
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
        with self._write_lock:
            conn = self._conn
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
        with self._write_lock:
            conn = self._conn
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
        sql_limit = min(max(cap * 10, 200), 2000)
        qvec = self.embedder.embed(q)
        scored: list[tuple[float, dict[str, Any]]] = []
        # Sprint 11 PERF-11-5: read 不持进程级锁（依赖 sqlite3 Connection mutex）
        conn = self._conn
        if project is not None and str(project).strip():
            rows = conn.execute(
                """
                SELECT source, source_id, project, category, content, embedding_json,
                       updated_at, access_count, last_accessed_at
                FROM memory_vectors
                WHERE project = ? OR project = ''
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (project.strip(), sql_limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT source, source_id, project, category, content, embedding_json,
                       updated_at, access_count, last_accessed_at
                FROM memory_vectors
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (sql_limit,),
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
        vector_sources: tuple[str, ...] | None = None,
    ) -> list[dict[str, Any]]:
        """Merge vector top-K with FTS hits (RRF-style), dedupe by content."""
        cap = limit if limit is not None else semantic_search_limit()
        vec_weight = hybrid_vector_weight()
        fts_weight = hybrid_fts_weight()

        vec_hits = self.search(query, project=project, limit=cap * 2)
        if vector_sources:
            allowed = set(vector_sources)
            vec_hits = [h for h in vec_hits if str(h.get("source") or "") in allowed]
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
        pairs = []
        for hit in hits:
            src = str(hit.get("source") or "")
            sid = str(hit.get("source_id") or "")
            if src and sid:
                pairs.append((src, sid))
        if not pairs:
            return
        with self._write_lock:
            conn = self._conn
            placeholders = " OR ".join(
                "(source = ? AND source_id = ?)" for _ in pairs
            )
            params: list[Any] = [now]
            for src, sid in pairs:
                params.extend([src, sid])
            conn.execute(
                f"""
                UPDATE memory_vectors
                SET access_count = access_count + 1, last_accessed_at = ?
                WHERE {placeholders}
                """,
                params,
            )
            conn.commit()

    def delete_source_prefix(self, source: str) -> int:
        with self._write_lock:
            conn = self._conn
            cur = conn.execute(
                "DELETE FROM memory_vectors WHERE source = ?",
                (source,),
            )
            conn.commit()
            return int(cur.rowcount or 0)

    def delete_by_category(self, category: str) -> int:
        cat = (category or "").strip()
        if not cat:
            return 0
        with self._write_lock:
            conn = self._conn
            cur = conn.execute(
                "DELETE FROM memory_vectors WHERE category = ?",
                (cat,),
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
        # Sprint 11 PERF-11-5: read 不持进程级锁
        conn = self._conn
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


def _is_experience_hit(hit: dict[str, Any]) -> bool:
    src = str(hit.get("source") or "").strip()
    if src == SOURCE_EXPERIENCE:
        return True
    if src in (SOURCE_OWNER_PROFILE, SOURCE_PROJECT):
        return False
    if src:
        return False
    raw_id = hit.get("id") or hit.get("source_id")
    if raw_id is None:
        return False
    try:
        int(raw_id)
        return True
    except (TypeError, ValueError):
        return False


def filter_experience_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [h for h in hits if _is_experience_hit(h)]


def enrich_experience_hit_tags(
    hits: list[dict[str, Any]],
    experience_store: Any | None,
) -> list[dict[str, Any]]:
    if not hits:
        return hits
    need_ids: list[int] = []
    for h in hits:
        if str(h.get("tags") or "").strip():
            continue
        if not _is_experience_hit(h):
            continue
        raw = h.get("id") or h.get("source_id")
        try:
            need_ids.append(int(raw))
        except (TypeError, ValueError):
            continue
    rows_by_id: dict[int, dict[str, Any]] = {}
    if need_ids and experience_store is not None and hasattr(experience_store, "fetch_by_ids"):
        try:
            rows_by_id = {int(r["id"]): r for r in experience_store.fetch_by_ids(need_ids)}
        except Exception as exc:
            logger.debug("enrich experience tags skipped: %s", exc)
    out: list[dict[str, Any]] = []
    for h in hits:
        item = dict(h)
        if not str(item.get("source") or "").strip():
            item["source"] = SOURCE_EXPERIENCE
        if item.get("id") is None:
            raw = item.get("source_id")
            try:
                item["id"] = int(raw)
            except (TypeError, ValueError):
                pass
        if not str(item.get("tags") or "").strip():
            rid = item.get("id")
            try:
                row = rows_by_id.get(int(rid)) if rid is not None else None
            except (TypeError, ValueError):
                row = None
            if row and row.get("tags"):
                item["tags"] = row["tags"]
        out.append(item)
    return out


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
        # Audit R2-2: write failures must preserve the stack trace so the
        # operator can diagnose embed OOM / DB lock / provider auth issues
        # that this code path silently swallowed before.
        logger.error(
            "Semantic index upsert failed for experience %s", row_id, exc_info=exc
        )


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


def _hybrid_experience_search_once(
    semantic: SemanticMemoryIndex | None,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
) -> tuple[list[dict[str, Any]], str, int, bool]:
    """Single-query hybrid; returns (hits, mode, fallbacks, degraded).

    ``degraded`` is True when any hybrid_search call raised and we had to
    fall back to FTS-only. The caller (``hybrid_experience_search``) records
    this flag in retrieval telemetry so /诊断 and the LLM can react.
    """
    fts_hits = fts_search(query, project=project, limit=limit * 2)
    mode = "fts" if semantic is None else "hybrid"
    fallbacks = 0
    degraded = False
    if semantic is None:
        out = fts_hits[:limit]
    else:
        try:
            out = semantic.hybrid_search(
                query,
                fts_hits,
                project=project,
                limit=limit,
                vector_sources=(SOURCE_EXPERIENCE,),
            )
        except Exception as exc:
            # Audit R2-2: degraded quality must be loud (ERROR + exc_info)
            # so ops sees the underlying embed OOM / DB lock / provider auth
            # error rather than a quiet warning that loses the stack.
            logger.error("Hybrid search failed, using FTS", exc_info=exc)
            out = fts_hits[:limit]
            mode = "fts-error-fallback"
            fallbacks += 1
            degraded = True
    if not out and project is not None:
        fallbacks += 1
        global_fts_hits = fts_search(query, project=None, limit=limit * 4)
        if semantic is None:
            out = global_fts_hits[:limit]
            mode = "fts-fallback-global"
        else:
            try:
                out = semantic.hybrid_search(
                    query,
                    global_fts_hits,
                    project=None,
                    limit=limit,
                    vector_sources=(SOURCE_EXPERIENCE,),
                )
                mode = "hybrid-fallback-global"
            except Exception as exc:
                logger.error("Hybrid global fallback failed, using FTS", exc_info=exc)
                out = global_fts_hits[:limit]
                mode = "fts-fallback-global"
                degraded = True
    return out, mode, fallbacks, degraded


def _should_use_subqueries(query: str) -> bool:
    """R2-2 helper: return True when subquery fan-out is enabled and useful."""
    if not query:
        return False
    try:
        from butler.memory.query_decompose import decompose_query, subquery_enabled
    except Exception:
        return False
    if not subquery_enabled():
        return False
    return len(decompose_query(query)) > 1


def _run_subquery_hybrid(
    semantic: SemanticMemoryIndex | None,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None,
    limit: int,
) -> tuple[list[dict[str, Any]], list[str], bool]:
    """R2-2 helper: fan out per-subquery, aggregate degraded flag."""
    from butler.memory.query_decompose import search_with_subqueries

    degraded_flags: list[bool] = []

    def _once(sub_q: str) -> list[dict[str, Any]]:
        hits, _, _fb, sub_degraded = _hybrid_experience_search_once(
            semantic, fts_search, sub_q, project=project, limit=limit
        )
        degraded_flags.append(sub_degraded)
        return hits

    out, sub_queries = search_with_subqueries(query, _once, limit=limit)
    return out, sub_queries, any(degraded_flags)


def _build_recall_telemetry_payload(
    mode: str,
    fallbacks: int,
    out: list[dict[str, Any]],
    q: str,
    sub_queries: list[str],
    degraded: bool,
) -> dict[str, Any]:
    """Audit R2-2: build the recall-quality payload for retrieval_telemetry.

    The payload is the contract between ``hybrid_experience_search`` and
    ``retrieval_telemetry.record_last_retrieval`` — it is also the only
    place where ``recall_degraded`` is set, so changes here are observable
    in ``/诊断`` via ``rag_last_recall_degraded``.
    """
    payload: dict[str, Any] = {
        "mode": mode if out else "none",
        "fallbacks": fallbacks,
        "candidates": len(out),
        "query": q,
        # True iff hybrid_search raised on any path and we fell back to FTS only.
        "recall_degraded": bool(degraded),
    }
    if sub_queries and len(sub_queries) > 1:
        payload["sub_queries"] = sub_queries
        payload["mode"] = mode or "hybrid-subquery"
    return payload


def hybrid_experience_search(
    semantic: SemanticMemoryIndex | None,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
    experience_store: Any | None = None,
) -> list[dict[str, Any]]:
    """FTS-only when semantic disabled; otherwise hybrid merge (optional sub-queries)."""
    q = str(query or "").strip()
    sub_queries: list[str] = []
    mode = "none"
    fallbacks = 0
    degraded = False
    out: list[dict[str, Any]] = []
    try:
        if _should_use_subqueries(q):
            out, sub_queries, degraded = _run_subquery_hybrid(
                semantic, fts_search, q, project=project, limit=limit
            )
            mode = "hybrid-subquery"
        else:
            out, mode, fallbacks, degraded = _hybrid_experience_search_once(
                semantic, fts_search, q, project=project, limit=limit
            )
    except Exception:
        out, mode, fallbacks, degraded = _hybrid_experience_search_once(
            semantic, fts_search, q, project=project, limit=limit
        )

    out = filter_experience_hits(out)
    out = enrich_experience_hit_tags(out, experience_store)
    _record_experience_access_from_hits(experience_store, out)
    try:
        from butler.execution_context import get_current_session_key
        from butler.memory.retrieval_telemetry import record_last_retrieval

        record_last_retrieval(
            get_current_session_key() or "",
            _build_recall_telemetry_payload(
                mode=mode,
                fallbacks=fallbacks,
                out=out,
                q=q,
                sub_queries=sub_queries,
                degraded=degraded,
            ),
        )
    except Exception as exc:
        logger.debug("once skipped: %s", exc)
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
