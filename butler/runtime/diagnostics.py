"""Runtime job stats for /诊断."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from butler.runtime import audit, loader, schedule
import logging


logger = logging.getLogger(__name__)

def _workspace_for_project(project_name: str) -> Path | None:
    from butler.project.manager import ProjectManager

    proj = ProjectManager().get_project((project_name or "").strip())
    if proj is None:
        return None
    return Path(proj.workspace)


def collect_runtime_stats(project_name: str, *, max_jobs: int = 6) -> dict[str, Any]:
    """Recent run summary per job for diagnostics."""
    name = (project_name or "").strip()
    push_queue_pending = 0
    try:
        from butler.config import get_butler_home

        qpath = get_butler_home() / "runtime" / "push_queue.jsonl"
        if qpath.is_file():
            push_queue_pending = sum(
                1 for ln in qpath.read_text(encoding="utf-8").splitlines() if ln.strip()
            )
    except Exception as exc:
        logger.debug("collect runtime stats skipped: %s", exc)
    out: dict[str, Any] = {
        "project": name,
        "enabled": os.getenv("BUTLER_RUNTIME_ENABLED", "1").strip().lower()
        in ("1", "true", "yes", "on"),
        "jobs": [],
        "has_jobs_file": False,
        "push_queue_pending": push_queue_pending,
    }
    if not name:
        return out
    ws = _workspace_for_project(name)
    if ws is None:
        return out
    jobs = loader.list_jobs(ws)
    if not jobs:
        return out
    out["has_jobs_file"] = True
    for job in jobs[: max(1, max_jobs)]:
        last = audit.latest_run(name, job.id)
        entry: dict[str, Any] = {
            "id": job.id,
            "mode": job.mode,
            "enabled": job.enabled,
            "schedule": schedule.format_schedule_hint(job.schedule),
            "next_run": schedule.next_run_iso(job.schedule) if job.schedule else None,
        }
        if last:
            entry["last_at"] = last.get("finished_at")
            entry["last_success"] = last.get("success")
            rpaths = last.get("report_paths")
            if rpaths:
                entry["report_paths"] = rpaths
        out["jobs"].append(entry)
    return out


def format_runtime_diagnostic_lines(project_name: str) -> list[str]:
    stats = collect_runtime_stats(project_name)
    if not stats.get("has_jobs_file"):
        return []
    pq = int(stats.get("push_queue_pending") or 0)
    lines = [
        f"运行时(runtime): {'开' if stats.get('enabled') else '关'} (BUTLER_RUNTIME_ENABLED)",
    ]
    if pq:
        lines.append(f"  推送队列: {pq} 条待重试（runtime due / butler runtime drain-push）")
    for j in stats.get("jobs") or []:
        en = "开" if j.get("enabled") else "关"
        last = ""
        if j.get("last_at"):
            ok = "成功" if j.get("last_success") else "失败"
            last = f" | 上次 {j['last_at']} ({ok})"
            rps = j.get("report_paths") or []
            if rps:
                last += f" | 报告 {rps[0]}"
        nxt = ""
        if j.get("next_run"):
            nxt = f" | 下次 {j['next_run']}"
        lines.append(
            f"  · {j['id']} [{j.get('mode')}, {en}]{last}{nxt}"
        )
    lines.append("  微信: /定时 /运行 <id>；改盘: /批准运行 <id>")
    try:
        from butler.runtime.failure_tracker import format_failure_streak_lines

        lines.extend(format_failure_streak_lines())
    except Exception as exc:
        logger.debug("format runtime diagnostic lines skipped: %s", exc)
    return lines
