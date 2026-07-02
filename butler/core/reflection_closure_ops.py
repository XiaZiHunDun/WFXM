"""Reflection closure path and persist helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort
from butler.env_parse import env_truthy


def experience_path_safe() -> Path:
    def _run() -> Path:
        from butler.core.reflexion_write import _experience_path as _reflex_path

        return _reflex_path()

    result = safe_best_effort(
        _run,
        label="reflection_closure.experience_path",
        default=Path.home() / ".butler" / "experiences" / "reflexion.jsonl",
    )
    return result if isinstance(result, Path) else Path.home() / ".butler" / "experiences" / "reflexion.jsonl"


def should_persist_reflect() -> bool:
    if not env_truthy("BUTLER_REFLECTION_CLOSURE", default=True):
        return False

    def _reflexion_write_on() -> bool:
        from butler.core.reflexion_write import reflexion_write_enabled

        return bool(reflexion_write_enabled())

    if safe_best_effort(_reflexion_write_on, label="reflection_closure.reflexion_write", default=False):
        return True
    return env_truthy("BUTLER_REFLECTION_CLOSURE_WRITE", default=False)
