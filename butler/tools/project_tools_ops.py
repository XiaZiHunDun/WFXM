"""Best-effort helpers for project tool allowlists (P0-A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.project import Project

logger = logging.getLogger(__name__)


def opencode_tool_enabled() -> bool:
    def _run() -> bool:
        from butler.extensions.opencode import opencode_enabled

        return bool(opencode_enabled())

    result = safe_best_effort(_run, label="project_tools.opencode_enabled", default=False)
    return bool(result)


_DEV_EXTRA_TOOLS = frozenset({
    "dev_status",
    "dev_verify",
    "dev_review",
    "dev_rollback",
    "dev_search_symbols",
    "run_pytest",
})


def dev_engine_extra_tools() -> set[str]:
    def _run() -> set[str]:
        from butler.dev_engine.dev_tools import dev_engine_enabled

        if not dev_engine_enabled():
            return set()
        return set(_DEV_EXTRA_TOOLS)

    result = safe_best_effort(_run, label="project_tools.dev_engine_enabled", default=set())
    return result if isinstance(result, set) else set()


def mcp_tool_allowed(name: str) -> bool:
    def _run() -> bool:
        from butler.mcp.naming import is_mcp_registered_name

        return bool(is_mcp_registered_name(name))

    result = safe_best_effort(_run, label="project_tools.mcp_allowed", default=False)
    return bool(result)


def workflow_step_tool_allowlist(project: "Project | None") -> set[str] | None:
    def _run() -> set[str] | None:
        from pathlib import Path

        from butler.execution_context import get_current_workflow_step
        from butler.permissions import get_workflow_step_tool_allowlist

        step_id = get_current_workflow_step()
        if not step_id:
            return None
        ws = Path(project.workspace) if project is not None else None
        allowlist = get_workflow_step_tool_allowlist(step_id, workspace=ws)
        return allowlist if isinstance(allowlist, set) else None

    result = safe_best_effort(
        _run,
        label="project_tools.workflow_step_allowlist",
        default=None,
    )
    return result if result is None or isinstance(result, set) else None


def optimize_tool_definitions_safe(filtered: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.core.schema_optimizer import optimize_tool_definitions

        return optimize_tool_definitions(filtered) or filtered

    result = safe_best_effort(
        _run,
        label="project_tools.optimize_schema",
        default=filtered,
    )
    return result if isinstance(result, list) else filtered
