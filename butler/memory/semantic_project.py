"""Project MEMORY.md ↔ semantic vector index helpers (P1)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from butler.memory.semantic_index import SOURCE_PROJECT, SemanticMemoryIndex
from butler.memory.semantic_project_ops import (
    apply_heading_boost,
    prefetch_with_subqueries,
    resolve_project_display_name,
    run_project_vector_upsert,
    vector_search_project,
)

if TYPE_CHECKING:
    from butler.memory.project_memory import ProjectMemory

logger = logging.getLogger(__name__)


def project_bullet_source_id(project_name: str, section: str, content: str) -> str:
    """Stable id aligned with ``reindex._index_project_dir``."""
    body = (content or "").strip()
    sec = (section or "Notes").strip() or "Notes"
    return f"{project_name}:{sec}:{hash(body) & 0xFFFFFFFF:08x}"


def pending_source_id(project_name: str, content: str) -> str:
    """Vector id for a Pending-queue line (removed on approve/reject)."""
    body = (content or "").strip()
    return f"{project_name}:Pending:{hash(body) & 0xFFFFFFFF:08x}"


def index_pending_memory_bullet(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    content: str,
) -> None:
    text = (content or "").strip()
    if semantic is None or not text or not (project_name or "").strip():
        return

    def _upsert() -> None:
        sid = pending_source_id(project_name, text)
        semantic.upsert(
            source=SOURCE_PROJECT,
            source_id=sid,
            content=text,
            project=project_name,
            category="project_pending",
        )
        from butler.memory.semantic_index import index_triplets_for_content

        index_triplets_for_content(
            semantic,
            text,
            project=project_name,
            source=SOURCE_PROJECT,
            source_ref=sid,
        )
        from butler.memory.vector_sync_telemetry import record_vector_sync

        record_vector_sync("project_pending", project=project_name)

    run_project_vector_upsert("pending_upsert", _upsert)


def sync_project_append_vectors(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    section: str,
    content: str,
    cls_result: str,
) -> None:
    """Upsert vectors after ProjectMemory.markdown.append (post_session, butler_remember, …)."""
    text = (content or "").strip()
    proj = (project_name or "").strip()
    if not text or not proj:
        return
    sec = (section or "Notes").strip() or "Notes"
    cls = (cls_result or "").strip().lower()
    if cls == "pending":
        index_pending_memory_bullet(semantic, proj, text)
    elif cls == "decision":
        index_project_memory_bullet(semantic, proj, "Decisions", text)
    elif cls == "fact":
        index_project_memory_bullet(semantic, proj, sec, text)


def index_project_memory_bullet(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    section: str,
    content: str,
) -> None:
    text = (content or "").strip()
    if semantic is None or not text or not (project_name or "").strip():
        return
    sec = (section or "Notes").strip() or "Notes"
    if sec == "Pending":
        return

    def _upsert() -> None:
        sid = project_bullet_source_id(project_name, sec, text)
        semantic.upsert(
            source=SOURCE_PROJECT,
            source_id=sid,
            content=text,
            project=project_name,
            category="project_memory",
        )
        from butler.memory.semantic_index import index_triplets_for_content

        index_triplets_for_content(
            semantic,
            text,
            project=project_name,
            source=SOURCE_PROJECT,
            source_ref=sid,
        )
        from butler.memory.vector_sync_telemetry import record_vector_sync

        record_vector_sync("project", project=project_name)

    run_project_vector_upsert("bullet_upsert", _upsert)


def invalidate_pending_vector(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    content: str,
) -> None:
    """Drop Pending-queue vector after approve or explicit removal."""
    if semantic is None or not (project_name or "").strip():
        return
    text = (content or "").strip()
    if not text:
        return

    def _delete() -> None:
        semantic.delete(SOURCE_PROJECT, pending_source_id(project_name, text))

    run_project_vector_upsert("pending_delete", _delete)


def _query_tokens(query: str) -> set[str]:
    from butler.memory.embedding import _tokenize

    return {t for t in _tokenize(query) if len(t) >= 2}


def search_project_memory_keywords(
    pmem: "ProjectMemory",
    query: str,
    *,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Lightweight token overlap on formal MEMORY bullets (no vectors)."""
    tokens = _query_tokens(query)
    if not tokens:
        return []
    scored: list[tuple[int, dict[str, Any]]] = []
    for item in pmem.markdown.list_formal_bullets():
        body = item.get("content") or ""
        body_tokens = _query_tokens(body)
        if not body_tokens:
            continue
        overlap = len(tokens & body_tokens)
        if overlap <= 0:
            continue
        scored.append(
            (
                overlap,
                {
                    "content": body,
                    "section": item.get("section") or "Notes",
                    "retrieval": "keyword",
                    "score": overlap,
                },
            )
        )
    scored.sort(key=lambda x: (x[0], len(x[1].get("content") or "")), reverse=True)
    return [item for _, item in scored[:limit]]


def search_project_memory_vectors(
    semantic: SemanticMemoryIndex | None,
    query: str,
    *,
    project: str,
    limit: int = 5,
) -> list[dict[str, Any]]:
    """Vector search over formal project MEMORY bullets (excludes Pending drafts)."""
    q = (query or "").strip()
    proj = (project or "").strip()
    if semantic is None or not q or not proj:
        return []
    raw = vector_search_project(semantic, q, project=proj, limit=limit)
    if raw is None:
        return []
    out: list[dict[str, Any]] = []
    for hit in raw:
        if hit.get("source") != SOURCE_PROJECT:
            continue
        if (hit.get("category") or "") == "project_pending":
            continue
        out.append(apply_heading_boost(dict(hit), q))
        if len(out) >= limit:
            break
    from butler.memory.retrieval_ranking import rerank_memory_hits

    return rerank_memory_hits(out)


def invalidate_project_memory_bullet(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    section: str,
    content: str,
) -> None:
    text = (content or "").strip()
    if semantic is None or not text:
        return

    def _delete() -> None:
        semantic.delete(
            SOURCE_PROJECT,
            project_bullet_source_id(project_name, section, text),
        )

    run_project_vector_upsert("bullet_delete", _delete)


def _prefetch_project_once(
    pmem: "ProjectMemory",
    query: str,
    *,
    project_name: str,
    semantic: SemanticMemoryIndex | None,
    limit: int,
    semantic_enabled: bool,
) -> tuple[list[dict[str, Any]], str]:
    q = (query or "").strip()
    if semantic_enabled and semantic is not None:
        hits = search_project_memory_vectors(
            semantic, q, project=project_name, limit=limit
        )
        if hits:
            return hits, "vector"
    kw = search_project_memory_keywords(pmem, q, limit=limit)
    if kw:
        return kw, "keyword"
    return [], "none"


def prefetch_project_memory_hits(
    pmem: "ProjectMemory",
    query: str,
    *,
    project_name: str,
    semantic: SemanticMemoryIndex | None,
    limit: int = 5,
    semantic_enabled: bool = True,
) -> tuple[list[dict[str, Any]], str]:
    """
    Query-aligned project bullets: vectors first, then keyword fallback.

    Returns (hits, mode) where mode is ``vector`` | ``keyword`` | ``none`` | ``*-subquery``.
    """
    q = (query or "").strip()
    if not q or not project_name:
        return [], "none"

    def _search(sub_q: str) -> list[dict[str, Any]]:
        hits, _ = _prefetch_project_once(
            pmem,
            sub_q,
            project_name=project_name,
            semantic=semantic,
            limit=limit,
            semantic_enabled=semantic_enabled,
        )
        return hits

    subquery_result = prefetch_with_subqueries(q, _search, limit=limit)
    if subquery_result is not None:
        return subquery_result
    return _prefetch_project_once(
        pmem,
        q,
        project_name=project_name,
        semantic=semantic,
        limit=limit,
        semantic_enabled=semantic_enabled,
    )


__all__ = [
    "index_pending_memory_bullet",
    "index_project_memory_bullet",
    "invalidate_pending_vector",
    "invalidate_project_memory_bullet",
    "prefetch_project_memory_hits",
    "project_bullet_source_id",
    "pending_source_id",
    "resolve_project_display_name",
    "search_project_memory_keywords",
    "search_project_memory_vectors",
    "sync_project_append_vectors",
]
