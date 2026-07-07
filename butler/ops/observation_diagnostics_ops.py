"""Best-effort observation store diagnostics (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from butler.core.best_effort import safe_best_effort


def observation_store_stats_safe(db_path: Path) -> dict[str, Any] | None:
    def _run() -> dict[str, Any]:
        from butler.memory.observation_store import ObservationStore

        return cast(dict[str, Any], ObservationStore(db_path).stats())

    result = safe_best_effort(
        _run,
        label="observation_diagnostics.stats",
        default=None,
    )
    return result if isinstance(result, dict) else None


def relative_db_path_safe(workspace: Path, db_path: Path, *, fallback: str) -> str:
    def _run() -> str:
        if db_path.is_file():
            return str(db_path.relative_to(workspace))
        return fallback

    result = safe_best_effort(
        _run,
        label="observation_diagnostics.rel_db_path",
        default=None,
    )
    if isinstance(result, str) and result.strip():
        return result
    return fallback
