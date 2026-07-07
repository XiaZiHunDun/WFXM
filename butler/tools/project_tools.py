"""Project-scoped tool allowlists from ``project.yaml``."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast
from butler.tools.project_tools_ops import opencode_tool_enabled
from butler.tools.project_tools_ops import dev_engine_extra_tools
from butler.tools.project_tools_ops import mcp_tool_allowed
from butler.tools.project_tools_ops import workflow_step_tool_allowlist
from butler.tools.registry import get_tool_definitions
from butler.tools.project_tools_ops import optimize_tool_definitions_safe
from butler.execution_context import get_current_session_key
from butler.project.manager import get_project_manager

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
    "list_workflows",
    "search_project_knowledge",
    "skills_list",
    "skill_view",
    "butler_remember",
    "butler_recall",
    "list_runtime_jobs",
    "run_runtime_job",
    "contact_add",
    "contact_find",
    "contact_update",
    "contact_delete",
    "contact_list",
    "memo_add",
    "memo_list",
    "memo_search",
    "memo_update",
    "memo_delete",
    "expense_add",
    "expense_summary",
    "expense_list",
    "expense_update",
    "expense_search",
    "expense_delete",
    "habit_create",
    "habit_checkin",
    "habit_stats",
    "habit_list",
    "habit_update",
    "habit_delete",
    "set_reminder",
    "list_reminders",
    "reminder_list_active",
    "cancel_reminder",
})

# Project Lead: read-only + orchestration (no write/shell even if listed in project.yaml).
_LEAD_READ_TOOLS = frozenset({
    "read_file",
    "list_directory",
    "search_files",
})
_PLAN_MODE_TOOLS = frozenset({
    "read_file",
    "list_directory",
    "search_files",
    "search_project_knowledge",
    "search_transcript",
    "skills_list",
    "skill_view",
    "butler_remember",
    "butler_recall",
})

_LEAD_EXTRA_TOOLS = frozenset({
    "delegate_task",
    "run_workflow",
    "list_workflows",
    "skills_list",
    "skill_view",
    "butler_remember",
    "butler_recall",
    "list_runtime_jobs",
    "run_runtime_job",
})

# Lead may opt in read-only network tools from project.yaml (no shell / no fetch by default).
_LEAD_NETWORK_TOOLS = frozenset({
    "web_search",
})

_DEV_EXTRA_TOOLS = frozenset({
    "dev_status",
    "dev_verify",
    "dev_review",
    "dev_rollback",
    "dev_search_symbols",
    "run_pytest",
})

# A3/T8: butler main loop must not inherit project mutating tools from project.yaml.
_BUTLER_BLOCKED_PROJECT_TOOLS = frozenset({
    "write_file",
    "patch",
    "delete_file",
    "terminal",
    "git_add",
    "git_commit",
    "execute_code",
})


def _butler_tools_from_project(mapped: set[str]) -> set[str]:
    """Read-only / orchestration tools from project.yaml; strip file/shell mutators."""
    return {name for name in mapped if name not in _BUTLER_BLOCKED_PROJECT_TOOLS}


def _mcp_allowlist_from_mapped(mapped: set[str]) -> set[str]:
    """Preserve project.yaml MCP opt-in (``mcp_*`` or explicit ``mcp_`` names)."""
    return {
        name
        for name in mapped
        if name == "mcp_*" or (isinstance(name, str) and name.startswith("mcp_"))
    }


def _lead_network_from_mapped(mapped: set[str]) -> set[str]:
    """Preserve project.yaml opt-in for read-only Lead network tools."""
    return {name for name in mapped if name in _LEAD_NETWORK_TOOLS}


def _lead_allowed_tools(mapped: set[str]) -> set[str]:
    """Lead read-only core + orchestration; honor MCP opt-in from project.yaml."""
    read_only = {n for n in mapped if n in _LEAD_READ_TOOLS}
    return (
        read_only
        | set(_LEAD_EXTRA_TOOLS)
        | _mcp_allowlist_from_mapped(mapped)
        | _lead_network_from_mapped(mapped)
    )


def _butler_allowed_tools(mapped: set[str]) -> set[str]:

    extras = set(_BUTLER_EXTRA_TOOLS)
    if opencode_tool_enabled():
        extras.add("opencode_task")
    return _butler_tools_from_project(mapped) | extras


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
    norm_early = role.replace("_agent", "").strip().lower()
    if project is None:
        if norm_early == "plan":
            return set(_PLAN_MODE_TOOLS)
        return None
    raw = [canonical_tool_name(n) for n in (project.tools or [])]
    mapped = {n for n in raw if n}
    if not mapped:
        return None
    norm = role.replace("_agent", "").strip().lower()
    modes = getattr(project, "tool_modes", None) or {}
    if isinstance(modes, dict) and modes:
        mode_list = modes.get(norm) or modes.get(role) or modes.get(role.replace("_agent", ""))
        if isinstance(mode_list, list) and mode_list:
            mode_set = {canonical_tool_name(str(n)) for n in mode_list if str(n).strip()}
            mode_set = {n for n in mode_set if n}
            if norm == "plan":
                return mode_set & set(_PLAN_MODE_TOOLS) if mode_set else set(_PLAN_MODE_TOOLS)
            if norm == "lead":
                read_only = mode_set & _LEAD_READ_TOOLS if mode_set else set(_LEAD_READ_TOOLS)
                return (
                    read_only
                    | set(_LEAD_EXTRA_TOOLS)
                    | _mcp_allowlist_from_mapped(mapped)
                    | _lead_network_from_mapped(mapped)
                )
            if norm in {"butler", "default", ""} or role == "butler":
                return _butler_allowed_tools(mode_set)
            return mode_set
    if norm == "plan":
        return set(_PLAN_MODE_TOOLS)
    if norm == "lead":
        return _lead_allowed_tools(mapped)
    if norm in {"butler", "default", ""} or role == "butler":
        return _butler_allowed_tools(mapped)
    if norm == "dev":

        return mapped | set(dev_engine_extra_tools())
    return mapped


def _tool_allowed(name: str, allowed: set[str]) -> bool:
    if name in allowed:
        return True
    if "mcp_*" in allowed:

        if mcp_tool_allowed(name):
            return True
    return False


def filter_tool_definitions(
    tools: list[dict[str, Any]],
    allowed: set[str] | None,
) -> list[dict[str, Any]]:
    if allowed is None:
        return list(tools)
    return [
        t for t in tools
        if _tool_allowed(str(t.get("function", {}).get("name") or ""), allowed)
    ]


def _workflow_step_tool_allowlist(project: "Project | None") -> set[str] | None:

    return cast(set[str] | None, workflow_step_tool_allowlist(project))


def intersect_allowed_names(
    base: set[str] | None,
    extra: set[str] | None,
) -> set[str] | None:
    if extra is None:
        return base
    if base is None:
        return set(extra)
    return base & extra


def get_tool_definitions_for_project(
    project: "Project | None" = None,
    *,
    role: str = "butler",
    optimize_schema: bool = True,
) -> list[dict[str, Any]]:


    all_tools = get_tool_definitions()
    allowed = allowed_tool_names_for_project(project, role=role)
    allowed = intersect_allowed_names(allowed, _workflow_step_tool_allowlist(project))
    filtered = filter_tool_definitions(all_tools, allowed)
    if not optimize_schema:
        return filtered

    return cast(list[dict[str, Any]], optimize_tool_definitions_safe(filtered))


def get_current_project_tools(*, role: str = "butler") -> list[dict[str, Any]]:

    pm = get_project_manager()
    session_key = str(get_current_session_key() or "").strip()
    project = pm.get_current(session_key=session_key)
    return get_tool_definitions_for_project(project, role=role)


__all__ = [
    "allowed_tool_names_for_project",
    "canonical_tool_name",
    "filter_tool_definitions",
    "get_current_project_tools",
    "get_tool_definitions_for_project",
    "intersect_allowed_names",
]
