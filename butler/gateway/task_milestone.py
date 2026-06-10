"""Antigravity-style task_boundary milestones for long WeChat turns."""

from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.gateway.outbound_bridge import GatewayOutboundBridge


def task_milestone_enabled() -> bool:
    from butler.env_parse import env_truthy, float_env

    return env_truthy("BUTLER_GATEWAY_TASK_MILESTONE", default=False)


def task_milestone_min_seconds() -> float:
    try:
        return max(30.0, float_env("BUTLER_GATEWAY_TASK_MILESTONE_SECONDS", 90))
    except ValueError:
        return 90.0


def build_milestone_text(bridge: "GatewayOutboundBridge", *, elapsed: int) -> str:
    """Format: 阶段名 | 正在做什么 | 下一步"""
    phase = "处理中"
    doing = "分析并调用工具"
    nxt = "完成后回复摘要；可发 /health"

    if bridge.delegate_role:
        phase = f"委派·{bridge.delegate_role}"
        doing = "子代理执行项目任务"
        nxt = "完成后推送摘要"
    elif bridge.workflow_name:
        phase = f"工作流·{bridge.workflow_name}"
        step = bridge.workflow_step or ""
        if bridge.workflow_step_total > 0:
            doing = f"步骤 {bridge.workflow_step_index}/{bridge.workflow_step_total} {step}".strip()
        else:
            doing = step or "执行工作流步骤"
        nxt = "工作流结束后汇报"
    elif bridge.last_tool_name:
        phase = f"工具·{bridge.last_tool_name}"
        doing = "等待工具结果"
        nxt = "继续推理或委派"

    preview = (getattr(bridge, "_stream_preview", "") or "").strip()
    if preview:
        snippet = preview[-80:].replace("\n", " ")
        doing = f"{doing} …{snippet}"

    return f"【进度】{phase} | {doing} | {nxt}（约 {elapsed} 秒）"


def maybe_schedule_task_milestone(bridge: Any) -> None:
    """Send at most one milestone per turn after ack threshold (requires ack already sent)."""
    if not task_milestone_enabled():
        return
    if getattr(bridge, "_closed", True) or getattr(bridge, "_final_sent", False):
        return
    if not getattr(bridge, "_ack_sent", False):
        return
    if getattr(bridge, "_task_milestone_sent", False):
        return
    started = getattr(bridge, "_started_at", 0.0) or 0.0
    elapsed = int(time.monotonic() - started) if started else 0
    if elapsed < int(task_milestone_min_seconds()):
        return

    text = build_milestone_text(bridge, elapsed=elapsed)
    if bridge.schedule_supplementary_reply(text, kind="task_milestone"):
        bridge._task_milestone_sent = True


__all__ = [
    "build_milestone_text",
    "maybe_schedule_task_milestone",
    "task_milestone_enabled",
    "task_milestone_min_seconds",
]
