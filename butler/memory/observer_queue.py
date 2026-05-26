"""PostToolUse observation queue → SQLite observation store."""

from __future__ import annotations

import hashlib
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from butler.env_parse import env_truthy
from butler.memory.observation_store import ObservationStore, observations_db_path

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_QUEUE: deque[dict[str, str]] = deque(maxlen=256)
_FLUSH_BATCH = 8


def observer_queue_enabled() -> bool:
    return env_truthy("BUTLER_MEMORY_OBSERVER_QUEUE", default=False)


def observations_path(workspace: Path) -> Path:
    return observations_db_path(Path(workspace))


def observations_db(workspace: Path) -> ObservationStore:
    return ObservationStore(observations_db_path(Path(workspace)))


def _resolve_workspace() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            return None
        proj = orch.project_manager.get_current()
        if proj is None:
            return None
        return Path(proj.workspace)
    except Exception:
        return None


def enqueue_tool_observation(
    *,
    session_key: str,
    tool: str,
    ok: bool,
    preview: str = "",
    path: str = "",
) -> None:
    if not observer_queue_enabled():
        return
    norm_path = str(path or "").strip().replace("\\", "/")
    norm_preview = str(preview or "").strip()
    row = {
        "row_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_key": str(session_key or "")[:64],
        "tool": str(tool or "")[:64],
        "ok": "1" if ok else "0",
        "path": norm_path[:256],
        "preview": norm_preview[:400],
        "title": f"{tool}:{norm_path or norm_preview[:40]}",
        "content_hash": hashlib.sha1(
            f"{session_key}|{tool}|{norm_path}|{norm_preview}|{int(bool(ok))}".encode("utf-8")
        ).hexdigest(),
    }
    with _LOCK:
        _QUEUE.append(row)
        pending = len(_QUEUE)
    if pending >= _FLUSH_BATCH:
        flush_observer_queue()


def flush_observer_queue(workspace: Path | None = None) -> int:
    """Drain in-memory queue to workspace observation DB."""
    ws = workspace or _resolve_workspace()
    if ws is None:
        return 0
    with _LOCK:
        if not _QUEUE:
            return 0
        batch = list(_QUEUE)
        _QUEUE.clear()
    try:
        return observations_db(ws).insert_many(batch)
    except Exception as exc:
        with _LOCK:
            for row in reversed(batch):
                _QUEUE.appendleft(row)
        logger.warning("observations.db write failed: %s", exc)
        return 0


def list_observations_for_path(workspace: Path, file_path: str, *, limit: int = 5) -> list[dict[str, str]]:
    path = observations_path(Path(workspace))
    if not path.is_file():
        return []
    try:
        return observations_db(Path(workspace)).list_for_path(file_path, limit=limit)
    except Exception:
        return []


__all__ = [
    "enqueue_tool_observation",
    "flush_observer_queue",
    "list_observations_for_path",
    "observations_db",
    "observer_queue_enabled",
    "observations_path",
]
