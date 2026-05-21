"""Project MEMORY.md ↔ semantic vector index helpers (P1)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

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
