"""Lifecycle command context best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def doctor_audit_workspace_from_ctx_safe(ctx: Any) -> Path | None:
    def _run() -> Path:
        proj = ctx.orchestrator.project_manager.get_current(session_key=ctx.session_key)
        if proj is None:
            raise ValueError("no active project for doctor audit")
        return Path(proj.workspace)

    result = safe_best_effort(
        _run,
        label="lifecycle_commands.doctor_workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None
