"""Persist delegate / workflow tasks under ~/.butler/runtime/tasks/."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def _tasks_root() -> Path:
    from butler.config import get_butler_settings

    root = get_butler_settings().butler_home / "runtime" / "tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


def create_task(
    *,
    session_key: str = "",
    role: str = "",
    task_preview: str = "",
    project: str = "",
) -> dict[str, Any]:
    task_id = new_task_id()
    now = datetime.now(timezone.utc).isoformat()
    record: dict[str, Any] = {
        "task_id": task_id,
        "session_key": str(session_key or "").strip() or "default",
        "role": str(role or "").strip(),
        "project": str(project or "").strip(),
        "task_preview": (task_preview or "")[:500],
        "status": "running",
        "created_at": now,
        "updated_at": now,
        "report_headline": "",
        "success": None,
    }
    _write(task_id, record)
    return record


def update_task(task_id: str, **fields: Any) -> dict[str, Any] | None:
    record = get_task(task_id)
    if record is None:
        return None
    record.update(fields)
    record["updated_at"] = datetime.now(timezone.utc).isoformat()
    _write(task_id, record)
    return record


def complete_task(
    task_id: str,
    *,
    success: bool,
    report_headline: str = "",
    summary: str = "",
) -> dict[str, Any] | None:
    return update_task(
        task_id,
        status="completed" if success else "failed",
        success=success,
        report_headline=(report_headline or "")[:300],
        summary=(summary or "")[:4000],
    )


def get_task(task_id: str) -> dict[str, Any] | None:
    path = _tasks_root() / f"{task_id}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def list_recent_tasks(session_key: str = "", *, limit: int = 5) -> list[dict[str, Any]]:
    root = _tasks_root()
    files = sorted(root.glob("task_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    sk = str(session_key or "").strip()
    out: list[dict[str, Any]] = []
    for path in files:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        if sk and str(data.get("session_key") or "") != sk:
            continue
        out.append(data)
        if len(out) >= max(1, limit):
            break
    return out


def _write(task_id: str, record: dict[str, Any]) -> Path:
    path = _tasks_root() / f"{task_id}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
