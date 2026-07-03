"""Runtime tools project resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def resolve_current_project_name_safe() -> str | None:
    def _run() -> str:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            raise ValueError("no orchestrator")
        proj = orch.project_manager.get_current()
        if proj is None:
            raise ValueError("no current project")
        name = str(getattr(proj, "name", "") or "").strip()
        if not name:
            raise ValueError("empty project name")
        return name

    result = safe_best_effort(
        _run,
        label="runtime_tools.project_name",
        default=None,
    )
    return result if isinstance(result, str) else None


def resolve_project_workspace_safe(project_name: str) -> str | None:
    def _run() -> str:
        from butler.project.manager import get_project_manager

        p = get_project_manager().get_project(project_name)
        if p is None:
            raise ValueError("project not found")
        ws = getattr(p, "workspace", None)
        if not ws:
            raise ValueError("empty workspace")
        return str(ws)

    result = safe_best_effort(
        _run,
        label="runtime_tools.project_workspace",
        default=None,
    )
    return result if isinstance(result, str) else None
