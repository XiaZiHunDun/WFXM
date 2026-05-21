"""Gateway slash commands for project runtime jobs."""

from __future__ import annotations

from typing import TYPE_CHECKING, Optional

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
) -> Optional[str]:
    """Handle /定时, /运行. Returns None if cmd not recognized."""
    if cmd in ("/定时", "/runtime", "/定时任务"):
        from butler.runtime.service import format_jobs_list_text

        name = _active_project_name(orchestrator)
        if not name:
            return "请先 /切换 到试点项目（如 灵文1号），再查看定时任务。"
        return format_jobs_list_text(name)

    if cmd not in ("/运行", "/run-job", "/运行任务"):
        return None

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
