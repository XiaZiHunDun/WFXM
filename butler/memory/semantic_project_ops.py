"""Best-effort vector/index helpers for project MEMORY (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.memory.project_memory import ProjectMemory
    from butler.memory.semantic_index import SemanticMemoryIndex


def resolve_project_display_name(pmem: "ProjectMemory") -> str:
    def _run() -> str:
        from butler.project import Project

        yaml = Path(pmem.project_dir) / "project.yaml"
        if yaml.is_file():
            return Project.from_yaml(yaml).name
        return Path(pmem.project_dir).name

    result = safe_best_effort(
        _run,
        label="semantic_project.display_name",
        default=None,
    )
    if isinstance(result, str) and result.strip():
        return result
    return Path(pmem.project_dir).name


def run_project_vector_upsert(label: str, fn) -> None:
    safe_best_effort(fn, label=f"semantic_project.{label}", default=None)


def vector_search_project(
    semantic: "SemanticMemoryIndex",
    query: str,
    *,
    project: str,
    limit: int,
) -> list[dict[str, Any]] | None:
    def _run() -> list[dict[str, Any]]:
        return semantic.search(query, project=project, limit=max(limit * 2, limit))

    return safe_best_effort(
        _run,
        label="semantic_project.vector_search",
        default=None,
    )


def apply_heading_boost(item: dict[str, Any], query: str) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.memory.chunking import heading_boost_factor

        out = dict(item)
        base = float(out.get("score") or 0.0)
        boost = heading_boost_factor(str(out.get("content") or ""), query)
        if boost != 1.0:
            out["score"] = round(base * boost, 6)
            out["heading_boost"] = round(boost, 4)
        return out

    result = safe_best_effort(
        _run,
        label="semantic_project.heading_boost",
        default=None,
    )
    return item if result is None else result


def prefetch_with_subqueries(
    query: str,
    search_fn,
    *,
    limit: int,
) -> tuple[list[dict[str, Any]], str] | None:
    """Return merged hits + mode when subquery path succeeds; None to fall through."""

    def _run() -> tuple[list[dict[str, Any]], str] | None:
        from butler.memory.query_decompose import decompose_query, search_with_subqueries, subquery_enabled

        if not subquery_enabled() or len(decompose_query(query)) <= 1:
            return None
        merged, _subs = search_with_subqueries(query, search_fn, limit=limit)
        if merged:
            return merged, "subquery"
        return [], "none"

    return safe_best_effort(
        _run,
        label="semantic_project.subquery_prefetch",
        default=None,
    )


__all__ = [
    "apply_heading_boost",
    "prefetch_with_subqueries",
    "resolve_project_display_name",
    "run_project_vector_upsert",
    "vector_search_project",
]
