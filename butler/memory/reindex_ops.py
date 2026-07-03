"""Semantic reindex best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.memory.butler_memory import ButlerMemory
from butler.memory.semantic_index import SemanticMemoryIndex

logger = logging.getLogger(__name__)


def sync_profile_vectors_safe(bm: ButlerMemory) -> int:
    def _run() -> int:
        return int(bm.sync_profile_vectors())

    result = safe_best_effort(_run, label="reindex.profile_vectors", default=0)
    return int(result or 0)


def project_name_from_yaml_safe(yaml: Path) -> str | None:
    def _run() -> str:
        from butler.project import Project

        return str(Project.from_yaml(yaml).name)

    result = safe_best_effort(_run, label="reindex.project_name", default=None)
    return str(result) if isinstance(result, str) and result else None


def refresh_project_facts_safe(pm: Any, project_dir: Path) -> None:
    def _run() -> None:
        pm.refresh_facts()

    safe_best_effort(_run, label="reindex.refresh_facts", default=None)


def load_project_memory_safe(project_dir: Path) -> tuple[Any, Any] | None:
    def _run() -> tuple[Any, Any]:
        from butler.memory.project_memory import ProjectMemory
        from butler.project import Project

        proj = Project.from_yaml(project_dir / "project.yaml")
        pm = ProjectMemory(project_dir)
        return proj, pm

    result = safe_best_effort(_run, label="reindex.load_project", default=None)
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], result[1]
    return None


def index_markdown_corpus_safe(
    semantic: SemanticMemoryIndex,
    project_dir: Path,
    *,
    project_name: str,
    workspace: Path,
) -> int:
    def _run() -> int:
        from butler.memory.chunking import (
            index_project_markdown_corpus,
            markdown_chunking_enabled,
        )

        if not markdown_chunking_enabled():
            return 0
        return int(
            index_project_markdown_corpus(
                semantic,
                project_dir,
                project_name=project_name,
                workspace=workspace,
            )
        )

    result = safe_best_effort(_run, label="reindex.markdown_corpus", default=0)
    return int(result or 0)


def index_project_bullet_safe(
    semantic: SemanticMemoryIndex,
    *,
    content: str,
    project_name: str,
    section: str,
    source_id: str,
) -> bool:
    def _run() -> None:
        from butler.memory.semantic_index import SOURCE_PROJECT, index_triplets_for_content

        semantic.upsert(
            source=SOURCE_PROJECT,
            source_id=source_id,
            content=content,
            project=project_name,
            category="project_memory",
        )
        index_triplets_for_content(
            semantic,
            content,
            project=project_name,
            source=SOURCE_PROJECT,
            source_ref=source_id,
        )

    result = safe_best_effort(_run, label="reindex.project_bullet", default=None)
    return result is not None
