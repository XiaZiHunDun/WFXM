"""Query relaxation chain when hybrid recall degrades (AP-10)."""

from __future__ import annotations

from typing import Any, Callable

NO_RESULT_SYSTEM_NOTE = (
    "【检索提示】本轮记忆检索已降级或返回空结果；请勿编造未检索到的内容。"
    "如需事实请改用 read_file / search_files 或请 Owner 补充。"
)


def relax_project_filter(project: str | None) -> str | None:
    """Drop project scoping on second pass (broader recall)."""
    if project:
        return None
    return project


def build_no_result_system_note() -> str:
    return NO_RESULT_SYSTEM_NOTE


def hybrid_search_with_relaxation(
    search_once: Callable[..., tuple[list[dict[str, Any]], str, int, bool]],
    semantic: Any,
    fts_search: Callable[..., list[dict[str, Any]]],
    query: str,
    *,
    project: str | None = None,
    limit: int = 8,
) -> tuple[list[dict[str, Any]], str, int, bool, str | None]:
    """Run hybrid once; if empty + degraded, retry without project filter.

    Returns (hits, mode, fallbacks, degraded, optional_system_note).
    """
    out, mode, fallbacks, degraded = search_once(
        semantic, fts_search, query, project=project, limit=limit,
    )
    note: str | None = None
    if not out and degraded and project:
        out, mode2, fb2, deg2 = search_once(
            semantic, fts_search, query, project=None, limit=limit,
        )
        mode = f"{mode}+relaxed"
        fallbacks += fb2 + 1
        degraded = degraded or deg2
    if not out and degraded:
        note = build_no_result_system_note()
    return out, mode, fallbacks, degraded, note


__all__ = [
    "NO_RESULT_SYSTEM_NOTE",
    "build_no_result_system_note",
    "hybrid_search_with_relaxation",
    "relax_project_filter",
]
