"""Project-scoped tool allowlists from ``project.yaml``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.project import Project

# Names in project.yaml may use legacy aliases from design docs.
_TOOL_NAME_ALIASES: dict[str, str] = {
    "edit_file": "patch",
    "search_code": "search_files",
    "run_shell": "terminal",
    "skill_list": "skills_list",
}

# Butler orchestration tools always available when a project is selected.
_BUTLER_EXTRA_TOOLS = frozenset({
    "delegate_task",
    "skills_list",
    "skill_view",
})


def canonical_tool_name(name: str) -> str:
    """Map project.yaml tool name to registry tool name."""
    key = str(name or "").strip()
    if not key:
        return ""
    return _TOOL_NAME_ALIASES.get(key, key)


def allowed_tool_names_for_project(
    project: "Project | None",
    *,
    role: str = "butler",
) -> set[str] | None:
    """Return allowed registry tool names, or ``None`` if unrestricted."""
    if project is None:
        return None
    raw = [canonical_tool_name(n) for n in (project.tools or [])]
    mapped = {n for n in raw if n}
    if not mapped:
        return None
    if role.replace("_agent", "") in {"butler", "default", ""} or role == "butler":
        return mapped | _BUTLER_EXTRA_TOOLS
    return mapped


def filter_tool_definitions(
    tools: list[dict],
    allowed: set[str] | None,
) -> list[dict]:
    if allowed is None:
        return list(tools)
    return [
        t for t in tools
        if t.get("function", {}).get("name") in allowed
    ]


def get_tool_definitions_for_project(
    project: "Project | None" = None,
    *,
    role: str = "butler",
) -> list[dict]:
    from butler.tools.registry import get_tool_definitions

    all_tools = get_tool_definitions()
    allowed = allowed_tool_names_for_project(project, role=role)
    return filter_tool_definitions(all_tools, allowed)


def get_current_project_tools(*, role: str = "butler") -> list[dict]:
    from butler.project_manager import get_project_manager

    pm = get_project_manager()
    project = pm.get_current() if pm.current_project else None
    return get_tool_definitions_for_project(project, role=role)


__all__ = [
    "allowed_tool_names_for_project",
    "canonical_tool_name",
    "filter_tool_definitions",
    "get_current_project_tools",
    "get_tool_definitions_for_project",
]
