"""Global runtime toolset profiles (complements per-project allowlists)."""

from __future__ import annotations

import os
from typing import Any

TOOLSET_FULL = "full"
TOOLSET_WECHAT_MINIMAL = "wechat_minimal"
TOOLSET_CRON = "cron"

_PROFILES: dict[str, frozenset[str] | None] = {
    TOOLSET_FULL: None,
    TOOLSET_WECHAT_MINIMAL: frozenset({
        "read_file",
        "search_files",
        "list_directory",
        "terminal",
        "web_search",
        "butler_recall",
        "butler_remember",
        "search_transcript",
        "skills_list",
        "skill_view",
        "delegate_task",
        "run_workflow",
        "list_runtime_jobs",
    }),
    TOOLSET_CRON: frozenset({
        "read_file",
        "butler_recall",
        "list_runtime_jobs",
        "run_runtime_job",
        "search_transcript",
    }),
}


def active_toolset() -> str:
    raw = os.getenv("BUTLER_TOOLSET", TOOLSET_FULL).strip().lower()
    if raw in _PROFILES:
        return raw
    return TOOLSET_FULL


def toolset_allowed_names(toolset: str | None = None) -> frozenset[str] | None:
    """Return allowed tool names for profile, or None for no global filter."""
    key = (toolset or active_toolset()).strip().lower()
    return _PROFILES.get(key, _PROFILES[TOOLSET_FULL])


def filter_definitions_by_toolset(
    definitions: list[dict[str, Any]],
    *,
    toolset: str | None = None,
) -> list[dict[str, Any]]:
    from butler.execution_context import get_current_loop_role

    if get_current_loop_role() == "butler":
        return definitions
    allowed = toolset_allowed_names(toolset)
    if allowed is None:
        return definitions
    out: list[dict[str, Any]] = []
    for spec in definitions:
        fn_raw = spec.get("function")
        fn = fn_raw if isinstance(fn_raw, dict) else spec
        name = str(fn.get("name") or spec.get("name") or "")
        if name in allowed or name.startswith("mcp_"):
            out.append(spec)
    return out


__all__ = [
    "TOOLSET_CRON",
    "TOOLSET_FULL",
    "TOOLSET_WECHAT_MINIMAL",
    "active_toolset",
    "filter_definitions_by_toolset",
    "toolset_allowed_names",
]
