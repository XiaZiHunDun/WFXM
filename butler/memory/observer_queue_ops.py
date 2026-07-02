"""Observer queue best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def migrate_observations_tsv_safe(workspace: Path, store: Any) -> None:
    def _run() -> None:
        from butler.memory.observation_migrate import migrate_tsv_if_needed

        migrate_tsv_if_needed(workspace, store=store)

    safe_best_effort(_run, label="observer_queue.migrate_tsv", default=None)


def resolve_observer_workspace_safe() -> Path | None:
    def _run() -> Path | None:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            return None
        proj = orch.project_manager.get_current()
        if proj is None:
            return None
        return Path(proj.workspace)

    result = safe_best_effort(_run, label="observer_queue.workspace", default=None)
    return result if isinstance(result, Path) else None


def flush_observation_batch_loud(
    ws: Path,
    batch: list[dict[str, str]],
    *,
    requeue: Any,
) -> int:
    try:
        from butler.memory.observer_queue import observations_db

        return int(observations_db(ws).insert_many(batch))
    except Exception as exc:
        requeue(batch)
        logger.warning("observations.db write failed: %s", exc)
        return 0


def list_observations_for_path_safe(
    workspace: Path,
    file_path: str,
    *,
    limit: int,
) -> list[dict[str, str]]:
    def _run() -> list[dict[str, str]]:
        from butler.memory.observer_queue import observations_db

        return observations_db(Path(workspace)).list_for_path(file_path, limit=limit)

    result = safe_best_effort(_run, label="observer_queue.list_path", default=[])
    return result if isinstance(result, list) else []
