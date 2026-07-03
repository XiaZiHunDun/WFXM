"""Reflexion experience path best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_project_experience_path_safe() -> Path | None:
    def _run() -> Path:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is None:
            raise ValueError("no project manager")
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            raise ValueError("no active project")
        return (
            Path(proj.workspace).expanduser().resolve()
            / ".butler"
            / "experiences"
            / "reflexion.jsonl"
        )

    result = safe_best_effort(
        _run,
        label="reflexion_write.experience_path",
        default=None,
    )
    return result if isinstance(result, Path) else None
