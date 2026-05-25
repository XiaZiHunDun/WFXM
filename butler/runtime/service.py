"""High-level runtime API for CLI and gateway."""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.project_manager import ProjectManager
from butler.runtime import approval, audit, loader, notify, runner, schedule
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
        appr = approval.get_approval(project_name, job.id)
        rows.append(
            {
                "id": job.id,
                "description": job.description,
                "mode": job.mode,
                "enabled": job.enabled,
                "schedule": schedule.format_schedule_hint(job.schedule),
                "next_run": schedule.next_run_iso(job.schedule) if job.schedule else None,
                "approved": appr is not None,
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
        extra = ""
        if r.get("next_run"):
            extra += f" | 下次 {r['next_run']}"
        if r["mode"] == "mutating" and r.get("approved"):
            extra += " | 已批准待执行"
        lines.append(
            f"• {r['id']} [{r['mode']}, {en}] {r['schedule']}{last}{extra}\n"
            f"  {r['description']}"
        )
    lines.append("")
    lines.append("只读: /运行 <任务id>")
    lines.append("改盘: /批准运行 <任务id>（须 jobs.yaml enabled 或显式批准）")
    lines.append("CLI: butler runtime run|due|approve --project " + project_name)
    return "\n".join(lines)


def run_job(
    project_name: str,
    job_id: str,
    *,
    skip_notify: bool = False,
    force: bool = False,
    approved_run: bool = False,
) -> dict[str, Any]:
    """Execute one job. Mutating jobs need valid approval (or approved_run after grant)."""
    if not runtime_enabled():
        return {"success": False, "error": "BUTLER_RUNTIME_ENABLED=0"}

    ws = _project_workspace(project_name)
    if ws is None:
        return {"success": False, "error": f"未知项目: {project_name}"}

    job = loader.find_job(ws, job_id)
    if job is None:
        return {"success": False, "error": f"未知任务: {job_id}"}

    if not job.enabled and not (force or approved_run):
        return {"success": False, "error": f"任务 {job_id} 已禁用（jobs.yaml enabled: false）"}

    if not job.is_readonly:
        if approval.approval_required(job) and not (
            approved_run or approval.is_approved(project_name, job_id)
        ):
            return {
                "success": False,
                "error": (
                    f"任务 {job_id} 为改盘任务，须先 /批准运行 {job_id} "
                    f"（有效期 {job.approval.expires_hours}h）"
                ),
            }

    if not audit.try_acquire_lock(project_name, job_id):
        return {"success": False, "error": f"任务 {job_id} 正在运行或锁未释放"}

    started_at = datetime.now(timezone.utc).isoformat()
    try:
        result = runner.execute_job(job, ws)
    finally:
        audit.release_lock(project_name, job_id)

    if not job.is_readonly and approval.approval_required(job):
        approval.consume_approval(project_name, job_id)

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
        "report_paths": result.get("report_paths") or [],
    }
    record_path = audit.write_run_record(
        project_name=project_name, job_id=job.id, payload=record
    )

    try:
        from butler.runtime.failure_tracker import record_job_outcome

        record_job_outcome(
            project_name,
            job.id,
            success=bool(result.get("success")),
            audit_path=str(record_path),
        )
    except Exception as exc:
        logger.debug("Failure streak tracking skipped: %s", exc)

    if not skip_notify:
        _maybe_notify(project_name, job, result, audit_path=str(record_path))

    out: dict[str, Any] = {
        "success": bool(result.get("success")),
        "job_id": job.id,
        "summary": record["summary"],
        "duration_seconds": result.get("duration_seconds"),
        "record_path": str(record_path),
        "returncode": result.get("returncode"),
        "report_paths": result.get("report_paths") or [],
    }
    if result.get("outcome"):
        out["outcome"] = result["outcome"]
    try:
        from butler.experiments.ledger import maybe_record_from_job_result

        exp_row = maybe_record_from_job_result(ws, job.id, result)
        if exp_row:
            out["experiment"] = exp_row
    except Exception as exc:
        logger.debug("Experiment ledger record skipped: %s", exc)
    return out


def approve_and_run(
    project_name: str,
    job_id: str,
    *,
    run_now: bool = True,
    skip_notify: bool = False,
) -> dict[str, Any]:
    """Grant approval; optionally execute mutating job immediately."""
    ws = _project_workspace(project_name)
    if ws is None:
        return {"success": False, "error": f"未知项目: {project_name}"}

    job = loader.find_job(ws, job_id)
    if job is None:
        return {"success": False, "error": f"未知任务: {job_id}"}

    if job.is_readonly:
        return {
            "success": False,
            "error": f"任务 {job_id} 为只读，请用 /运行 {job_id}",
        }

    rec = approval.grant_approval(
        project_name,
        job_id,
        expires_hours=job.approval.expires_hours,
    )
    if not run_now:
        return {
            "success": True,
            "job_id": job_id,
            "approved_until": rec.get("approved_until"),
            "message": f"已批准 {job_id}，有效期至 {rec.get('approved_until')}",
        }

    return run_job(
        project_name,
        job_id,
        skip_notify=skip_notify,
        force=True,
        approved_run=True,
    )


def _maybe_notify(
    project_name: str,
    job: JobDef,
    result: dict[str, Any],
    *,
    audit_path: str = "",
) -> None:
    ok = bool(result.get("success"))
    if ok and not job.notify.on_success:
        return
    if not ok and not job.notify.on_failure:
        return
    status = "成功" if ok else "失败"
    title = f"[Butler] {project_name} / {job.id} {status}"
    body = (result.get("summary") or result.get("stderr") or "")[: job.notify.max_summary_chars]
    if not ok and audit_path:
        tail = f"\n\n审计: {audit_path}"
        room = job.notify.max_summary_chars - len(tail)
        if room > 0:
            body = body[:room] + tail
        else:
            body = f"审计: {audit_path}"
    notify.push_runtime_message(title, body)


def _notify_mutating_due(project_name: str, job: JobDef) -> dict[str, Any]:
    if not approval.should_notify_mutating_due(project_name, job.id):
        return {"job_id": job.id, "pending_approval": True, "notified": False}
    body = approval.format_approval_hint(project_name, job)
    notify.push_runtime_message(f"[Butler] {project_name} 待批准", body)
    approval.mark_mutating_due_notified(project_name, job.id)
    return {"job_id": job.id, "pending_approval": True, "notified": True}


def list_due_jobs(project_name: str) -> list[str]:
    """Readonly jobs due now (cron match)."""
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


def list_due_mutating_jobs(project_name: str) -> list[JobDef]:
    ws = _project_workspace(project_name)
    if ws is None:
        return []
    out: list[JobDef] = []
    for job in loader.list_jobs(ws, enabled_only=True):
        if job.is_readonly:
            continue
        if job.schedule and schedule.job_is_due(job.schedule):
            out.append(job)
    return out


def discover_runtime_projects() -> list[str]:
    """Projects with a non-empty ``runtime/jobs.yaml``."""
    names: list[str] = []
    for proj in ProjectManager().list_projects():
        ws = Path(proj.workspace)
        jf = loader.load_jobs_file(ws)
        if jf and jf.jobs:
            names.append(proj.name)
    return sorted(names)


def run_due_jobs(
    project_name: str,
    *,
    skip_notify: bool = False,
) -> list[dict[str, Any]]:
    """Run due readonly jobs; notify Owner for due mutating jobs awaiting approval."""
    if not runtime_enabled():
        return [{"success": False, "error": "BUTLER_RUNTIME_ENABLED=0"}]

    try:
        from butler.runtime.push_queue import drain_push_queue

        drain_push_queue(max_items=2)
    except Exception as exc:
        logger.debug("Push queue drain skipped: %s", exc)

    results: list[dict[str, Any]] = []
    for jid in list_due_jobs(project_name):
        results.append(run_job(project_name, jid, skip_notify=skip_notify))

    for job in list_due_mutating_jobs(project_name):
        if approval.is_approved(project_name, job.id):
            results.append(
                run_job(
                    project_name,
                    job.id,
                    skip_notify=skip_notify,
                    approved_run=True,
                )
            )
        else:
            entry = _notify_mutating_due(project_name, job)
            if not skip_notify:
                pass
            results.append(entry)

    return results


def run_due_jobs_all(*, skip_notify: bool = False) -> list[dict[str, Any]]:
    """Run due jobs for every project that has runtime/jobs.yaml."""
    combined: list[dict[str, Any]] = []
    for name in discover_runtime_projects():
        for item in run_due_jobs(name, skip_notify=skip_notify):
            item.setdefault("project", name)
            combined.append(item)
    return combined
