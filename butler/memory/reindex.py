"""Rebuild local semantic vector index from experience.db and project MEMORY.md."""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from butler.memory.butler_memory import ButlerMemory
from butler.memory.project_memory import ProjectMemory, normalize_section_name
from butler.memory.semantic_config import semantic_memory_enabled
from butler.memory.semantic_index import (
    SOURCE_PROJECT,
    SemanticMemoryIndex,
    index_experience_row,
)

logger = logging.getLogger(__name__)

_CONVERSATION = "conversation"
_MEMORY_BULLET_RE = re.compile(r"^-\s*\[[^\]]+\]\s*(.+)$")


def reindex_semantic_memory(
    butler_home: Path,
    *,
    tenant_id: str = "default",
    projects_dir: Path | None = None,
    project_name: str | None = None,
    index_experience: bool = True,
    index_project_memory: bool = True,
    clear_vectors: bool = True,
) -> dict[str, Any]:
    """
    Rebuild ``memory_vectors.db`` from on-disk Butler/project memory.

    Does not call cloud APIs (uses configured local hashing embedder).
    """
    home = Path(butler_home).expanduser().resolve()
    bm = ButlerMemory(home, tenant_id=tenant_id)
    if bm.semantic is None:
        return {
            "ok": False,
            "error": "BUTLER_SEMANTIC_MEMORY is not enabled (set to 1 in .env)",
            "indexed_experience": 0,
            "indexed_project_bullets": 0,
        }

    semantic: SemanticMemoryIndex = bm.semantic
    stats: dict[str, Any] = {
        "ok": True,
        "tenant_id": bm.tenant_id,
        "model_id": semantic.model_id,
        "cleared": 0,
        "indexed_experience": 0,
        "indexed_project_bullets": 0,
        "indexed_markdown_chunks": 0,
        "skipped_conversation": 0,
        "projects_scanned": 0,
    }

    if clear_vectors:
        stats["cleared"] = _clear_vector_table(semantic)
        tri_clear = bm.triplet_index()
        if tri_clear is not None:
            stats["cleared_triplets"] = tri_clear.clear_all()

    if index_experience:
        rows = bm.experience.get_recent(limit=10_000)
        for row in rows:
            cat = (row.get("category") or "").strip()
            if cat == _CONVERSATION:
                stats["skipped_conversation"] += 1
                continue
            rid = row.get("id")
            if rid is None:
                continue
            index_experience_row(
                semantic,
                int(rid),
                project=str(row.get("project") or ""),
                category=cat,
                content=str(row.get("content") or ""),
            )
            stats["indexed_experience"] += 1

    if index_project_memory:
        import os

        raw = os.getenv("BUTLER_PROJECTS_DIR", "").strip()
        if projects_dir is not None:
            pdir = Path(projects_dir).expanduser().resolve()
        elif raw:
            pdir = Path(raw).expanduser().resolve()
        else:
            pdir = Path.cwd() / "projects"

        for proj_path in _iter_project_dirs(pdir, project_name):
            stats["projects_scanned"] += 1
            bullets, chunks = _index_project_dir(proj_path, semantic)
            stats["indexed_project_bullets"] += bullets
            stats["indexed_markdown_chunks"] += chunks

    try:
        stats["indexed_profile_vectors"] = bm.sync_profile_vectors()
    except Exception as exc:
        logger.warning("Profile vector sync during reindex failed: %s", exc)
        stats["indexed_profile_vectors"] = 0

    tri = bm.triplet_index()
    if tri is not None:
        stats["triplet_rows"] = tri.count()
    else:
        stats["triplet_rows"] = 0

    stats["vector_rows"] = semantic.count_rows()
    return stats


def _clear_vector_table(semantic: SemanticMemoryIndex) -> int:
    with semantic._lock:
        conn = semantic._conn
        cur = conn.execute("SELECT COUNT(*) FROM memory_vectors")
        n = int(cur.fetchone()[0] or 0)
        conn.execute("DELETE FROM memory_vectors")
        conn.commit()
        return n


def _iter_project_dirs(projects_dir: Path, only_name: str | None) -> list[Path]:
    root = Path(projects_dir).expanduser().resolve()
    if not root.is_dir():
        return []
    out: list[Path] = []
    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue
        yaml = child / "project.yaml"
        if not yaml.is_file():
            continue
        if only_name:
            try:
                from butler.project import Project

                proj = Project.from_yaml(yaml)
                if proj.name != only_name:
                    continue
            except Exception:
                continue
        out.append(child)
    return out


def _index_project_dir(project_dir: Path, semantic: SemanticMemoryIndex) -> tuple[int, int]:
    try:
        from butler.project import Project

        proj = Project.from_yaml(project_dir / "project.yaml")
        pm = ProjectMemory(project_dir)
        try:
            pm.refresh_facts()
        except Exception as exc:
            logger.debug("facts refresh during reindex skipped for %s: %s", project_dir, exc)
    except Exception as exc:
        logger.warning("Skip project %s: %s", project_dir, exc)
        return 0, 0

    chunk_count = 0
    try:
        from butler.memory.chunking import (
            index_project_markdown_corpus,
            markdown_chunking_enabled,
        )

        if markdown_chunking_enabled():
            chunk_count = index_project_markdown_corpus(
                semantic,
                project_dir,
                project_name=proj.name,
                workspace=proj.workspace,
            )
    except Exception as exc:
        logger.warning("Markdown corpus index failed for %s: %s", project_dir, exc)

    count = 0
    if chunk_count > 0:
        return count, chunk_count

    sections = pm.markdown.get_all_sections()
    for section, body in sections.items():
        if section == "Pending":
            continue
        section = normalize_section_name(section)
        for line in (body or "").splitlines():
            m = _MEMORY_BULLET_RE.match(line.strip())
            if not m:
                continue
            content = m.group(1).strip()
            if not content:
                continue
            source_id = f"{proj.name}:{section}:{hash(content) & 0xFFFFFFFF:08x}"
            try:
                semantic.upsert(
                    source=SOURCE_PROJECT,
                    source_id=source_id,
                    content=content,
                    project=proj.name,
                    category="project_memory",
                )
                from butler.memory.semantic_index import index_triplets_for_content

                index_triplets_for_content(
                    semantic,
                    content,
                    project=proj.name,
                    source=SOURCE_PROJECT,
                    source_ref=source_id,
                )
                count += 1
            except Exception as exc:
                logger.warning("Project bullet index failed: %s", exc)
    return count, chunk_count


def ensure_semantic_enabled_msg() -> str | None:
    if semantic_memory_enabled():
        return None
    return (
        "BUTLER_SEMANTIC_MEMORY=0 — 将 .env 中设为 1 后重试，或确认已加载 .env"
    )
