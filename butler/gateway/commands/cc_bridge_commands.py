"""Claude Code CLI bridge slash commands (/cc-bridge)."""

from __future__ import annotations

from typing import Optional

from butler.gateway.command_registry import CommandContext, CommandDef, register, require_owner


def _resolve_workspace(ctx: CommandContext) -> tuple[str, str]:
  pm = ctx.orchestrator.project_manager
  proj = pm.get_current(session_key=ctx.session_key)
  if proj is None:
      return "", ""
  ws = str(getattr(proj, "workspace", "") or "").strip()
  name = str(getattr(proj, "name", "") or "").strip()
  return ws, name


def _cmd_cc_bridge(ctx: CommandContext) -> Optional[str]:
    gate = require_owner(ctx)
    if gate:
        return gate

    from butler.runtime.cc_bridge import (
        cc_bridge_enabled,
        format_cc_bridge_status,
        push_cc_bridge_completion,
        submit_cc_bridge_job,
    )

    arg = (ctx.arg or "").strip()
    if not arg:
        return format_cc_bridge_status(session_key=ctx.session_key)

    if not cc_bridge_enabled():
        return (
            "CC CLI 桥接未启用。\n"
            "请设 BUTLER_CC_BRIDGE=1 并 restart gateway，或执行：\n"
            "  python3 scripts/apply-butler-env-profile.py dev-remote"
        )

    ws, proj_name = _resolve_workspace(ctx)
    if not ws:
        return "无活跃项目，请先 /切换 到目标项目"

    def _on_done(job) -> None:
        push_cc_bridge_completion(job)

    job = submit_cc_bridge_job(
        session_key=ctx.session_key,
        task=arg,
        workspace=ws,
        project_name=proj_name,
        run_async=True,
        on_complete=_on_done,
    )
    if job.status == "failed":
        return f"提交失败：{job.error}"

    return (
        f"已提交 CC CLI 任务（{job.job_id}）\n"
        f"项目：{proj_name or ws}\n"
        f"任务：{arg[:300]}\n"
        "完成后将微信通知；可查 /cc-bridge 看最近记录。"
    )


_CC_COMMANDS: list[CommandDef] = [
    CommandDef(
        "/cc-bridge",
        ("/批准 cc-bridge", "/cc"),
        "开发工具",
        "Claude Code CLI 重任务（opt-in）",
        handler=_cmd_cc_bridge,
    ),
]


def register_cc_bridge_commands() -> None:
    for cmd in _CC_COMMANDS:
        register(cmd)


register_cc_bridge_commands()
