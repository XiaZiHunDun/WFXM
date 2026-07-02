"""Best-effort helpers for memory CLI (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_project_workspace_safe(project: str) -> Path | None:
    def _run() -> Path | None:
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_project(project)
        if proj is None or not getattr(proj, "workspace", None):
            return None
        return Path(str(proj.workspace)).expanduser().resolve()

    result = safe_best_effort(_run, label="memory_cli.project_workspace", default=None)
    return result if isinstance(result, Path) else None
