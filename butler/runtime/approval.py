"""Mutating job approval store (~/.butler/runtime/approvals/)."""

from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from butler.config import get_butler_settings
from butler.runtime.schema import JobDef


def _approvals_root() -> Path:
    root = get_butler_settings().butler_home / "runtime" / "approvals"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug(name: str) -> str:
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in (name or "project"))


def _record_path(project_name: str, job_id: str) -> Path:
    return _approvals_root() / _slug(project_name) / f"{job_id}.json"


def _notify_stamp_path(project_name: str, job_id: str) -> Path:
    return _approvals_root() / _slug(project_name) / f"{job_id}.due_notified"


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def grant_approval(
    project_name: str,
    job_id: str,
    *,
    expires_hours: int = 48,
) -> dict[str, Any]:
    """Grant one-shot approval valid until approved_until (UTC ISO)."""
    now = datetime.now(timezone.utc)
    until = now + timedelta(hours=max(1, int(expires_hours)))
    record = {
        "project": project_name,
        "job_id": job_id,
        "approved_at": now.isoformat(),
        "approved_until": until.isoformat(),
        "consumed": False,
    }
    path = _record_path(project_name, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def get_approval(project_name: str, job_id: str) -> dict[str, Any] | None:
    rec = _read_json(_record_path(project_name, job_id))
    if rec is None:
        return None
    if rec.get("consumed"):
        return None
    until_raw = rec.get("approved_until")
    if not until_raw:
        return None
    try:
        until = datetime.fromisoformat(str(until_raw).replace("Z", "+00:00"))
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
    except ValueError:
        return None
    if datetime.now(timezone.utc) >= until:
        return None
    return rec


def is_approved(project_name: str, job_id: str) -> bool:
    return get_approval(project_name, job_id) is not None


def consume_approval(project_name: str, job_id: str) -> None:
    path = _record_path(project_name, job_id)
    rec = _read_json(path)
    if rec is None:
        return
    rec["consumed"] = True
    rec["consumed_at"] = datetime.now(timezone.utc).isoformat()
    try:
        path.write_text(json.dumps(rec, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        pass


def approval_required(job: JobDef) -> bool:
    if job.is_readonly:
        return False
    return bool(job.approval.required)


def should_notify_mutating_due(
    project_name: str,
    job_id: str,
    *,
    cooldown_seconds: int = 21600,
) -> bool:
    """Avoid spamming Owner WeChat on every timer tick."""
    path = _notify_stamp_path(project_name, job_id)
    if not path.is_file():
        return True
    try:
        age = time.time() - path.stat().st_mtime
        return age >= cooldown_seconds
    except OSError:
        return True


def mark_mutating_due_notified(project_name: str, job_id: str) -> None:
    path = _notify_stamp_path(project_name, job_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(datetime.now(timezone.utc).isoformat(), encoding="utf-8")
    except OSError:
        pass


def format_approval_hint(project_name: str, job: JobDef) -> str:
    hours = job.approval.expires_hours
    return (
        f"任务 `{job.id}`（改盘）待批准。\n"
        f"请在 {hours}h 内回复：/批准运行 {job.id}\n"
        f"项目: {project_name}"
    )
