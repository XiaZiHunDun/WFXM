"""High-level runtime API for CLI and gateway."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.project_manager import ProjectManager
from butler.runtime import audit, loader, notify, runner, schedule
from butler.runtime.schema import JobDef

logger = logging.getLogger(__name__)


def runtime_enabled() -> bool:
    v = os.getenv("BUTLER_RUNTIME_ENABLED", "1").strip().lower()
    return v in ("1", "true", "yes", "on")


def _project_workspace(project_name: str) -> Path | None:
    pm = ProjectManager()
    proj = pm.get_project(project_name)
    if proj is None:
        return None
    return Path(proj.workspace)


def list_jobs_status(project_name: str) -> list[dict[str, Any]]:
    ws = _project_workspace(project_name)
    if ws is None:
        return []
    rows: list[dict[str, Any]] = []
    for job in loader.list_jobs(ws):
        last = audit.latest_run(project_name, job.id)
        rows.append(
            {
                "id": job.id,
                "description": job.description,
                "mode": job.mode,
                "enabled": job.enabled,
                "schedule": schedule.format_schedule_hint(job.schedule),
                "last_success": last.get("success") if last else None,
                "last_at": last.get("finished_at") if last else None,
            }
        )
    return rows


def format_jobs_list_text(project_name: str) -> str:
    rows = list_jobs_status(project_name)
    if not rows:
        return f"项目「{project_name}」无 runtime/jobs.yaml 或为空。"
    lines = [f"定时任务 — {project_name}", ""]
    for r in rows:
        en = "开" if r["enabled"] else "关"
        last = ""
        if r.get("last_at"):
            ok = "成功" if r.get("last_success") else "失败"
            last = f" | 上次 {r['last_at']} ({ok})"
        lines.append(
            f"• {r['id']} [{r['mode']}, {en}] {r['schedule']}{last}\n"
            f"  {r['description']}"
        )
    lines.append("")
    lines.append("手动运行（只读）: /运行 <任务id>")
    lines.append("CLI: butler runtime run <id> --project " + project_name)
    return "\n".join(lines)


def run_job(
    project_name: str,
    job_id: str,
    *,
    skip_notify: bool = False,
    force: bool = False,
) -> dict[str, Any]:
    """Execute one job. Mutating jobs require enabled=true (3c adds approval gate)."""
    if not runtime_enabled():
        return {"success": False, "error": "BUTLER_RUNTIME_ENABLED=0"}

    ws = _project_workspace(project_name)
    if ws is None:
        return {"success": False, "error": f"未知项目: {project_name}"}

    job = loader.find_job(ws, job_id)
    if job is None:
        return {"success": False, "error": f"未知任务: {job_id}"}

    if not job.enabled and not force:
        return {"success": False, "error": f"任务 {job_id} 已禁用（jobs.yaml enabled: false）"}

    if not job.is_readonly:
        return {
            "success": False,
            "error": (
                f"任务 {job_id} 为 mutating，阶段 3a 仅支持只读任务。"
                "请使用 /批准运行（阶段 3c）或保持 enabled: false。"
            ),
        }

    if not audit.try_acquire_lock(project_name, job_id):
        return {"success": False, "error": f"任务 {job_id} 正在运行或锁未释放"}

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = runner.execute_job(job, ws)
    finally:
        audit.release_lock(project_name, job_id)

    finished_at = datetime.now(timezone.utc).isoformat()
    record = {
        "project": project_name,
        "job_id": job.id,
        "mode": job.mode,
        "started_at": started_at,
        "finished_at": finished_at,
        "success": bool(result.get("success")),
        "duration_seconds": result.get("duration_seconds"),
        "summary": (result.get("summary") or "")[: job.notify.max_summary_chars],
        "returncode": result.get("returncode"),
    }
    record_path = audit.write_run_record(
        project_name=project_name, job_id=job.id, payload=record
    )

    if not skip_notify:
        _maybe_notify(project_name, job, result)

    return {
        "success": bool(result.get("success")),
        "job_id": job.id,
        "summary": record["summary"],
        "duration_seconds": result.get("duration_seconds"),
        "record_path": str(record_path),
    }


def _maybe_notify(project_name: str, job: JobDef, result: dict[str, Any]) -> None:
    ok = bool(result.get("success"))
    if ok and not job.notify.on_success:
        return
    if not ok and not job.notify.on_failure:
        return
    status = "成功" if ok else "失败"
    title = f"[Butler] {project_name} / {job.id} {status}"
    body = (result.get("summary") or result.get("stderr") or "")[: job.notify.max_summary_chars]
    notify.push_runtime_message(title, body)


def list_due_jobs(project_name: str) -> list[str]:
    ws = _project_workspace(project_name)
    if ws is None:
        return []
    due: list[str] = []
    for job in loader.list_jobs(ws, enabled_only=True):
        if not job.is_readonly:
            continue
        if job.schedule and schedule.job_is_due(job.schedule):
            due.append(job.id)
    return due


def run_due_jobs(
    project_name: str,
    *,
    skip_notify: bool = False,
) -> list[dict[str, Any]]:
    results = []
    for jid in list_due_jobs(project_name):
        results.append(run_job(project_name, jid, skip_notify=skip_notify))
    return results
