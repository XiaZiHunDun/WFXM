"""Project knowledge search best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def multi_scope_recall_safe(query: str, *, limit: int) -> str | None:
    def _run() -> str:
        from butler.memory.corpus_router import corpus_routing_enabled, multi_scope_recall

        if not corpus_routing_enabled() or not query:
            raise ValueError("corpus routing disabled or empty query")
        return str(multi_scope_recall(query, limit=limit) or "")

    result = safe_best_effort(
        _run,
        label="knowledge_search.multi_scope",
        default=None,
    )
    return result if isinstance(result, str) else None


def resolve_project_workspace_for_enrich_safe(project_name: str) -> Path | None:
    if not project_name:
        return None

    def _run() -> Path:
        from butler.project.manager import get_project_manager

        project = get_project_manager().get_project(project_name)
        if project is None or not getattr(project, "workspace", None):
            raise ValueError("project workspace unavailable")
        return Path(project.workspace).expanduser().resolve()

    result = safe_best_effort(
        _run,
        label="knowledge_search.project_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None
