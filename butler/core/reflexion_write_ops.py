"""Reflexion experience path best-effort helpers (P0-A).

Uses Result type for explicit error handling instead of implicit exception raising.
"""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort
from butler.core.effects import Err, Ok, Result


def resolve_project_experience_path() -> Result[Path, str]:
    """Resolve the project experience path using Result type for explicit error handling."""
    from butler.execution_context import get_current_orchestrator, get_current_session_key

    orch = get_current_orchestrator()
    pm = getattr(orch, "project_manager", None) if orch else None
    if pm is None:
        return Err("no project manager")
    proj = pm.get_current(session_key=str(get_current_session_key() or ""))
    if proj is None:
        return Err("no active project")
    return Ok(
        Path(proj.workspace).expanduser().resolve()
        / ".butler"
        / "experiences"
        / "reflexion.jsonl"
    )


def resolve_project_experience_path_safe() -> Path | None:
    """Best-effort wrapper that returns None on failure."""
    result = safe_best_effort(
        resolve_project_experience_path,
        label="reflexion_write.experience_path",
        default=None,
    )
    if isinstance(result, Result):
        return result.value if result.is_ok() else None
    return result if isinstance(result, Path) else None
