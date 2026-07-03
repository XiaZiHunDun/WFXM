"""Skills project sync workspace resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def default_project_name_safe() -> str:
    def _run() -> str:
        from butler.config import load_settings

        return str(load_settings().default_project or "").strip()

    result = safe_best_effort(
        _run,
        label="skills_project_sync.default_project_name",
        default="",
    )
    return str(result or "").strip()


def default_project_stack_workspace_safe(project_name: str) -> Path | None:
    name = str(project_name or "").strip()
    if not name:
        return None

    def _run() -> Path:
        from butler.project.manager import get_project_manager

        project = get_project_manager().get_project(name)
        workspace = getattr(project, "workspace", None) if project is not None else None
        if not workspace:
            raise ValueError("project workspace missing")
        ws = Path(str(workspace)).expanduser().resolve()
        if not (ws / "stack.yaml").is_file():
            raise ValueError("stack.yaml missing")
        return ws

    result = safe_best_effort(
        _run,
        label="skills_project_sync.stack_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None
