"""Bridge AgentLoop tools to Butler Runtime jobs (readonly without approval)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def _resolve_project_name(project: str | None = None) -> tuple[str | None, str | None]:
    name = (project or "").strip()
    if name:
        return name, None
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is not None:
            proj = orch.project_manager.get_current()
            if proj is not None:
                return str(getattr(proj, "name", "") or ""), None
    except Exception as exc:
        logger.debug("Runtime tool project resolve: %s", exc)
    return None, "No active project; pass project or /切换 first."


def _tool_list_runtime_jobs(project: str | None = None, **_) -> str:
    from butler.runtime.service import list_jobs_status, runtime_enabled

    if not runtime_enabled():
        return json.dumps({
            "ok": False,
            "error": "BUTLER_RUNTIME_ENABLED=0",
            "code": "RUNTIME_DISABLED",
        })
    proj, err = _resolve_project_name(project)
    if err:
        return json.dumps({"ok": False, "error": err})
    rows = list_jobs_status(proj or "")
    return json.dumps({"ok": True, "project": proj, "jobs": rows})


def _tool_run_runtime_job(
    job_id: str,
    project: str | None = None,
    **_,
) -> str:
    from butler.runtime import loader
    from butler.runtime.service import run_job, runtime_enabled

    jid = (job_id or "").strip()
    if not jid:
        return json.dumps({"ok": False, "error": "job_id is required"})

    if not runtime_enabled():
        return json.dumps({
            "ok": False,
            "error": "BUTLER_RUNTIME_ENABLED=0",
            "code": "RUNTIME_DISABLED",
        })

    proj, err = _resolve_project_name(project)
    if err:
        return json.dumps({"ok": False, "error": err})

    pm_ws = None
    try:
        from butler.project_manager import get_project_manager

        p = get_project_manager().get_project(proj or "")
        if p is not None:
            pm_ws = p.workspace
    except Exception:
        pass

    if pm_ws is not None:
        job = loader.find_job(pm_ws, jid)
        if job is not None and not job.is_readonly:
            return json.dumps({
                "ok": False,
                "error": (
                    f"Job {jid} is mutating; agent cannot run it directly. "
                    f"Use gateway /批准运行 {jid} or CLI: butler runtime approve."
                ),
                "code": "RUNTIME_MUTATING_REQUIRES_APPROVAL",
                "job_id": jid,
                "mode": job.mode,
            })

    out = run_job(proj or "", jid, skip_notify=True)
    payload: dict[str, Any] = {
        "ok": bool(out.get("success")),
        "project": proj,
        "job_id": jid,
        "success": out.get("success"),
        "summary": out.get("summary"),
        "duration_seconds": out.get("duration_seconds"),
        "record_path": out.get("record_path"),
        "returncode": out.get("returncode"),
        "report_paths": out.get("report_paths") or [],
    }
    if out.get("outcome"):
        payload["outcome"] = out["outcome"]
    if out.get("error"):
        payload["error"] = out["error"]
        payload["ok"] = False
    return json.dumps(payload, ensure_ascii=False)


def register_runtime_tools(register: Callable[..., None]) -> None:
    register(
        name="list_runtime_jobs",
        description=(
            "List runtime jobs from projects/<name>/runtime/jobs.yaml "
            "(schedules, mode, last run). Requires BUTLER_RUNTIME_ENABLED=1."
        ),
        schema={
            "type": "object",
            "properties": {
                "project": {
                    "type": "string",
                    "description": "Project name (default: current /切换 project)",
                },
            },
        },
        handler=_tool_list_runtime_jobs,
        toolset="runtime",
    )

    register(
        name="run_runtime_job",
        description=(
            "Execute a readonly runtime job by id (same as /运行). "
            "Mutating jobs are rejected — use /批准运行. skip_notify for agent calls."
        ),
        schema={
            "type": "object",
            "properties": {
                "job_id": {"type": "string", "description": "Job id from jobs.yaml"},
                "project": {
                    "type": "string",
                    "description": "Project name (default: current)",
                },
            },
            "required": ["job_id"],
        },
        handler=_tool_run_runtime_job,
        toolset="runtime",
    )
