"""Gateway slash commands for project runtime jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator


def _active_project_name(orchestrator: "ButlerOrchestrator") -> str:
    pm = orchestrator.project_manager
    proj = pm.get_current()
    return proj.name if proj else ""


def handle_runtime_command(
    orchestrator: "ButlerOrchestrator",
    cmd: str,
    arg: str,
    *,
    platform: str = "",
    external_id: str | None = None,
    session_key: str = "",
) -> Optional[str]:
    """Handle /定时, /运行, /批准运行. Returns None if cmd not recognized.

    Sprint 11 SEC-11-1: /运行 + /批准运行 路径加 owner gate。
    """
    if cmd in ("/定时", "/runtime", "/定时任务"):
        from butler.runtime.service import format_jobs_list_text

        name = _active_project_name(orchestrator)
        if not name:
            return "请先 /切换 到试点项目（如 灵文1号），再查看定时任务。"
        return format_jobs_list_text(name)

    # Sprint 11 SEC-11-1: /批准运行 改盘操作需 Owner 守门
    if cmd in ("/批准运行", "/approve-run", "/批准任务"):
        if not is_gateway_owner(
            platform=platform, external_id=external_id, session_key=session_key
        ):
            return owner_required_message()
        job_id = (arg or "").strip()
        if not job_id:
            return "用法: /批准运行 <任务id>\n例: /批准运行 publish-preflight"
        name = _active_project_name(orchestrator)
        if not name:
            return "请先 /切换 到试点项目。"
        from butler.runtime.service import approve_and_run

        out = approve_and_run(name, job_id, run_now=True)
        if out.get("error"):
            return f"批准/运行失败: {out['error']}"
        if out.get("message") and not out.get("summary"):
            return str(out["message"])
        ok = "成功" if out.get("success") else "失败"
        summary = (out.get("summary") or "").strip()
        lines = [f"已批准并执行任务 {job_id}（{ok}）。"]
        if summary:
            lines.append("")
            lines.append(summary[:1200])
        return "\n".join(lines)

    if cmd not in ("/运行", "/run-job", "/运行任务"):
        return None

    # Sprint 11 SEC-11-1: /运行 改盘操作需 Owner 守门
    if not is_gateway_owner(
        platform=platform, external_id=external_id, session_key=session_key
    ):
        return owner_required_message()

    job_id = (arg or "").strip()
    if not job_id:
        return "用法: /运行 <任务id>\n例: /运行 factory-status-daily\n先发送 /定时 查看列表。"

    name = _active_project_name(orchestrator)
    if not name:
        return "请先 /切换 到试点项目。"

    from butler.runtime.service import run_job

    out = run_job(name, job_id)
    if out.get("error"):
        return f"运行失败: {out['error']}"
    ok = "成功" if out.get("success") else "失败"
    summary = (out.get("summary") or "").strip()
    lines = [f"任务 {job_id} 已执行（{ok}）。"]
    if summary:
        lines.append("")
        lines.append(summary[:1200])
    return "\n".join(lines)
