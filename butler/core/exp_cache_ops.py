"""Experience LLM cache path/write best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_llm_cache_path_safe() -> Path:
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
            / "llm_cache.jsonl"
        )

    result = safe_best_effort(
        _run,
        label="exp_cache.resolve_path",
        default=None,
    )
    if isinstance(result, Path):
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
