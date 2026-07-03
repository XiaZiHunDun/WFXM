"""Tool audit JSONL path resolution best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def resolve_butler_home_safe() -> Path:
    def _run() -> Path:
        from butler.config import get_settings

        return Path(get_settings().butler_home).expanduser()

    result = safe_best_effort(
        _run,
        label="audit_persist.butler_home",
        default=None,
    )
    if isinstance(result, Path):
        return result
    return Path.home() / ".butler"
