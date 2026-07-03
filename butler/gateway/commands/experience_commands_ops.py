"""Experience command workspace resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def workspace_from_command_ctx_safe(ctx: Any) -> Path | None:
    def _run() -> Path:
        proj = ctx.orchestrator.project_manager.active_project
        if proj is None or not hasattr(proj, "workspace"):
            raise ValueError("no active project workspace")
        ws = Path(proj.workspace)
        if not ws.is_dir():
            raise ValueError("workspace is not a directory")
        return ws

    result = safe_best_effort(
        _run,
        label="experience_commands.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None
