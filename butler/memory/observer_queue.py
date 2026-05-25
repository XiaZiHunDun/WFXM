"""PostToolUse observation queue → `.butler/observations.tsv` (claude-mem subset)."""

from __future__ import annotations

import csv
import logging
import threading
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_OBS_NAME = "observations.tsv"
_FIELDNAMES = ("row_id", "timestamp", "session_key", "tool", "ok", "path", "preview", "title")
_LOCK = threading.Lock()
_QUEUE: deque[dict[str, str]] = deque(maxlen=256)
_FLUSH_BATCH = 8


def observer_queue_enabled() -> bool:
    return env_truthy("BUTLER_MEMORY_OBSERVER_QUEUE", default=False)


def observations_path(workspace: Path) -> Path:
    return Path(workspace).expanduser().resolve() / ".butler" / _OBS_NAME


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
    row = {
        "row_id": uuid.uuid4().hex[:12],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "session_key": str(session_key or "")[:64],
        "tool": str(tool or "")[:64],
        "ok": "1" if ok else "0",
        "path": str(path or "")[:256],
        "preview": str(preview or "")[:400],
        "title": f"{tool}:{path or preview[:40]}",
    }
    with _LOCK:
        _QUEUE.append(row)
        pending = len(_QUEUE)
    if pending >= _FLUSH_BATCH:
        flush_observer_queue()


def flush_observer_queue(workspace: Path | None = None) -> int:
    """Drain in-memory queue to workspace TSV."""
    ws = workspace or _resolve_workspace()
    if ws is None:
        return 0
    with _LOCK:
        if not _QUEUE:
            return 0
        batch = list(_QUEUE)
        _QUEUE.clear()
    path = observations_path(ws)
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.is_file()
    try:
        with path.open("a", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=_FIELDNAMES, delimiter="\t", extrasaction="ignore")
            if not exists:
                writer.writeheader()
            for row in batch:
                writer.writerow({k: row.get(k, "") for k in _FIELDNAMES})
    except OSError as exc:
        logger.warning("observations.tsv append failed: %s", exc)
        return 0
    return len(batch)


def list_observations_for_path(workspace: Path, file_path: str, *, limit: int = 5) -> list[dict[str, str]]:
    path = observations_path(Path(workspace))
    if not path.is_file():
        return []
    norm = str(file_path or "").strip().replace("\\", "/")
    rows: list[dict[str, str]] = []
    try:
        with path.open("r", encoding="utf-8", newline="") as fh:
            for row in csv.DictReader(fh, delimiter="\t"):
                p = str(row.get("path") or "").replace("\\", "/")
                if norm and p and (norm in p or p in norm):
                    rows.append(dict(row))
    except OSError:
        return []
    return rows[-limit:]


__all__ = [
    "enqueue_tool_observation",
    "flush_observer_queue",
    "list_observations_for_path",
    "observer_queue_enabled",
    "observations_path",
]
