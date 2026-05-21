"""Project MEMORY.md ↔ semantic vector index helpers (P1)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

from typing import Any

from butler.memory.semantic_index import SOURCE_PROJECT, SemanticMemoryIndex

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


def resolve_project_display_name(pmem: "ProjectMemory") -> str:
    try:
        from butler.project import Project

        yaml = Path(pmem.project_dir) / "project.yaml"
        if yaml.is_file():
            return Project.from_yaml(yaml).name
    except Exception:
        pass
    return Path(pmem.project_dir).name


def index_pending_memory_bullet(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    content: str,
) -> None:
    text = (content or "").strip()
    if semantic is None or not text or not (project_name or "").strip():
        return
    try:
        semantic.upsert(
            source=SOURCE_PROJECT,
            source_id=pending_source_id(project_name, text),
            content=text,
            project=project_name,
            category="project_pending",
        )
    except Exception as exc:
        logger.warning("Pending memory vector upsert failed: %s", exc)


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
    try:
        semantic.upsert(
            source=SOURCE_PROJECT,
            source_id=project_bullet_source_id(project_name, sec, text),
            content=text,
            project=project_name,
            category="project_memory",
        )
    except Exception as exc:
        logger.warning("Project memory vector upsert failed: %s", exc)


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
    try:
        semantic.delete(SOURCE_PROJECT, pending_source_id(project_name, text))
    except Exception as exc:
        logger.warning("Pending vector delete failed: %s", exc)


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
    try:
        raw = semantic.search(q, project=proj, limit=max(limit * 2, limit))
    except Exception as exc:
        logger.warning("Project memory vector search failed: %s", exc)
        return []
    out: list[dict[str, Any]] = []
    for hit in raw:
        if hit.get("source") != SOURCE_PROJECT:
            continue
        if (hit.get("category") or "") == "project_pending":
            continue
        out.append(hit)
        if len(out) >= limit:
            break
    return out


def invalidate_project_memory_bullet(
    semantic: SemanticMemoryIndex | None,
    project_name: str,
    section: str,
    content: str,
) -> None:
    text = (content or "").strip()
    if semantic is None or not text:
        return
    try:
        semantic.delete(
            SOURCE_PROJECT,
            project_bullet_source_id(project_name, section, text),
        )
    except Exception as exc:
        logger.warning("Project bullet vector delete failed: %s", exc)


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

    Returns (hits, mode) where mode is ``vector`` | ``keyword`` | ``none``.
    """
    q = (query or "").strip()
    if not q or not project_name:
        return [], "none"
    hits: list[dict[str, Any]] = []
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
