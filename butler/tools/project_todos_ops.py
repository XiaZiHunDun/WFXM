"""Project todos workspace resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def get_active_project_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        proj = orch.project_manager.active_project
        if proj is None or not getattr(proj, "workspace", None):
            raise ValueError("no active project workspace")
        return Path(proj.workspace)

    result = safe_best_effort(
        _run,
        label="project_todos.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None
