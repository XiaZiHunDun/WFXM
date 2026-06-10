"""PostToolUse observation queue → SQLite observation store."""

from __future__ import annotations

import atexit
import hashlib
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from butler.memory_settings import resolve_memory_config
from butler.memory.observation_store import ObservationStore, observations_db_path

logger = logging.getLogger(__name__)

_LOCK = threading.Lock()
_QUEUES: dict[str, deque[dict[str, str]]] = {}
_FLUSH_BATCH = 8


def observer_queue_enabled() -> bool:
    return resolve_memory_config().observer_queue_enabled


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


def _workspace_key(workspace: Path) -> str:
    return str(Path(workspace).expanduser().resolve())


def _queue_for_key(key: str) -> deque[dict[str, str]]:
    q = _QUEUES.get(key)
    if q is None:
        q = deque(maxlen=256)
        _QUEUES[key] = q
    return q


def _queue_for(workspace: Path) -> deque[dict[str, str]]:
    return _queue_for_key(_workspace_key(workspace))


def enqueue_tool_observation(
    *,
    session_key: str,
    tool: str,
    ok: bool,
    preview: str = "",
    path: str = "",
    workspace: Path | None = None,
) -> None:
    if not observer_queue_enabled():
        return
    ws = workspace or _resolve_workspace()
    if ws is None:
        logger.debug("skip observation queue without workspace")
        return
    key = _workspace_key(ws)
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
        queue = _queue_for_key(key)
        was_full = len(queue) >= (queue.maxlen or 256)
        queue.append(row)
        pending = len(queue)
    if was_full:
        logger.warning("observation queue at capacity (%d) — oldest entry discarded", queue.maxlen)
    if pending >= _FLUSH_BATCH:
        flush_observer_queue(ws)


def flush_observer_queue(workspace: Path | None = None) -> int:
    """Drain in-memory queue to workspace observation DB."""
    ws = workspace or _resolve_workspace()
    if ws is None:
        return 0
    key = _workspace_key(ws)
    with _LOCK:
        queue = _QUEUES.get(key)
        if not queue:
            return 0
        batch = list(queue)
        queue.clear()
    try:
        return observations_db(ws).insert_many(batch)
    except Exception as exc:
        with _LOCK:
            queue = _queue_for(ws)
            for row in reversed(batch):
                queue.appendleft(row)
        logger.warning("observations.db write failed: %s", exc)
        return 0


def flush_all_observer_queues() -> int:
    total = 0
    with _LOCK:
        workspaces = list(_QUEUES.keys())
    for key in workspaces:
        total += flush_observer_queue(Path(key))
    return total


def clear_observer_queue() -> None:
    with _LOCK:
        _QUEUES.clear()


def list_observations_for_path(workspace: Path, file_path: str, *, limit: int = 5) -> list[dict[str, str]]:
    path = observations_path(Path(workspace))
    if not path.is_file():
        return []
    try:
        return observations_db(Path(workspace)).list_for_path(file_path, limit=limit)
    except Exception:
        return []


__all__ = [
    "clear_observer_queue",
    "enqueue_tool_observation",
    "flush_all_observer_queues",
    "flush_observer_queue",
    "list_observations_for_path",
    "observations_db",
    "observer_queue_enabled",
    "observations_path",
]

atexit.register(flush_all_observer_queues)
