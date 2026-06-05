"""Persist delegate / workflow tasks under ~/.butler/runtime/tasks/."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy
from butler.io.safe_load import safe_load_json


def _tasks_root() -> Path:
    from butler.config import get_butler_settings

    root = get_butler_settings().butler_home / "runtime" / "tasks"
    root.mkdir(parents=True, exist_ok=True)
    return root


def new_task_id() -> str:
    return f"task_{uuid.uuid4().hex[:12]}"


def task_stale_minutes() -> int:
    try:
        return max(5, int(os.getenv("BUTLER_TASK_STALE_MINUTES", "") or "60"))
    except ValueError:
        return 60


def task_stale_auto_fail() -> bool:
    return env_truthy("BUTLER_TASK_STALE_AUTO_FAIL", default=False)


def _parse_iso(ts: str) -> datetime | None:
    raw = str(ts or "").strip()
    if not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def is_task_stale(record: dict[str, Any], *, now: datetime | None = None) -> bool:
    if str(record.get("status") or "") != "running":
        return False
    updated = _parse_iso(str(record.get("updated_at") or record.get("created_at") or ""))
    if updated is None:
        return False
    ref = now or datetime.now(timezone.utc)
    if updated.tzinfo is None:
        updated = updated.replace(tzinfo=timezone.utc)
    return ref - updated > timedelta(minutes=task_stale_minutes())


def mark_stale_tasks(
    session_key: str = "",
    *,
    auto_fail: bool | None = None,
) -> list[dict[str, Any]]:
    """Return stale running tasks; optionally mark failed."""
    do_fail = task_stale_auto_fail() if auto_fail is None else auto_fail
    stale: list[dict[str, Any]] = []
    root = _tasks_root()
    sk = str(session_key or "").strip()
    for path in root.glob("task_*.json"):
        # Audit R2-19: corrupt task record used to silently skip.
        # safe_load renames the corrupt file for forensic retention,
        # logs WARNING with exc_info, and records the event for /诊断.
        data = safe_load_json(path, default=None, kind="runtime_task")
        if not isinstance(data, dict):
            continue
        if sk and str(data.get("session_key") or "") != sk:
            continue
        if not is_task_stale(data):
            continue
        stale.append(data)
        if do_fail:
            update_task(
                str(data.get("task_id") or ""),
                status="failed",
                success=False,
                report_headline="任务超时（stale）",
                summary="running 超过配置时限，已自动标记失败。",
            )
    return stale


def delegate_group_id(session_key: str, *, parent_task_id: str = "") -> str:
    """Stable group id for related delegate/workflow tasks in one session."""
    import hashlib

    base = f"{str(session_key or 'default').strip()}:{str(parent_task_id or 'root').strip()}"
    return hashlib.sha256(base.encode("utf-8")).hexdigest()[:16]


def create_task(
    *,
    session_key: str = "",
    role: str = "",
    task_preview: str = "",
    project: str = "",
    group_id: str = "",
) -> dict[str, Any]:
    from butler.delegate.subagent_permissions import make_child_session_key

    task_id = new_task_id()
    sk = str(session_key or "").strip() or "default"
    now = datetime.now(timezone.utc).isoformat()
    gid = str(group_id or "").strip() or delegate_group_id(sk)
    record: dict[str, Any] = {
        "task_id": task_id,
        "session_key": sk,
        "group_id": gid,
        "child_session_key": make_child_session_key(sk, task_id),
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
    # Audit R2-19: corrupt task record used to silently return None.
    # safe_load renames the corrupt file for forensic retention,
    # logs WARNING with exc_info, and records the event for /诊断.
    data = safe_load_json(path, default=None, kind="runtime_task")
    return data if isinstance(data, dict) else None


def count_running_tasks(session_key: str = "") -> int:
    sk = str(session_key or "").strip()
    n = 0
    for path in _tasks_root().glob("task_*.json"):
        # Audit R2-19: corrupt task record used to silently skip.
        data = safe_load_json(path, default=None, kind="runtime_task")
        if not isinstance(data, dict):
            continue
        if str(data.get("status") or "") != "running":
            continue
        if sk and str(data.get("session_key") or "") != sk:
            continue
        n += 1
    return n


def list_recent_tasks(session_key: str = "", *, limit: int = 5) -> list[dict[str, Any]]:
    root = _tasks_root()
    files = sorted(root.glob("task_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    sk = str(session_key or "").strip()
    out: list[dict[str, Any]] = []
    for path in files:
        # Audit R2-19: corrupt task record used to silently skip.
        data = safe_load_json(path, default=None, kind="runtime_task")
        if not isinstance(data, dict):
            continue
        if sk and str(data.get("session_key") or "") != sk:
            continue
        row = dict(data)
        if is_task_stale(row):
            row["stale"] = True
        out.append(row)
        if len(out) >= max(1, limit):
            break
    return out


def _write(task_id: str, record: dict[str, Any]) -> Path:
    from butler.io.atomic_write import atomic_write_text

    path = _tasks_root() / f"{task_id}.json"
    atomic_write_text(path, json.dumps(record, ensure_ascii=False, indent=2))
    return path
