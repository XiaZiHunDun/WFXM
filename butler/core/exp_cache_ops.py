"""Experience LLM cache path/write best-effort helpers (P0-A).

Uses Result type for explicit error handling instead of implicit exception raising.
"""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort
from butler.core.effects import Err, Ok, Result


def resolve_llm_cache_path() -> Result[Path, str]:
    """Resolve the LLM cache path using Result type for explicit error handling."""
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
        / "llm_cache.jsonl"
    )


def resolve_llm_cache_path_safe() -> Path:
    """Best-effort wrapper with fallback to home directory."""
    result = safe_best_effort(
        resolve_llm_cache_path,
        label="exp_cache.resolve_path",
        default=None,
    )
    if isinstance(result, Result):
        if result.is_ok():
            return result.value
    elif isinstance(result, Path):
        return result
    return Path.home() / ".butler" / "experiences" / "llm_cache.jsonl"


def write_llm_cache_file_safe(path: Path, text: str) -> None:
    def _atomic() -> None:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, text)

    def _plain() -> None:
        path.write_text(text, encoding="utf-8")

    if safe_best_effort(_atomic, label="exp_cache.atomic_write", default=None) is None:
        safe_best_effort(_plain, label="exp_cache.plain_write", default=None)
