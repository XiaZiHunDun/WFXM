"""Uniform Owner-facing gate hints: what happened + what to send next."""

from __future__ import annotations


def workflow_gate_pending_hint(*, workflow: str, step_id: str) -> str:
    from butler.human_gate import _workflow_auto_resume_enabled

    wf = str(workflow or "").strip() or "工作流"
    step = str(step_id or "").strip() or "当前步骤"
    lines = [
        f"工作流「{wf}」步骤「{step}」等待确认。",
        "回复 **确认** 继续，或 **取消** 中止。",
    ]
    if _workflow_auto_resume_enabled():
        lines.append("下一步：确认后将**自动续跑**工作流（无需再发 /工作流）。")
    else:
        lines.append(f"下一步：确认后发送 **/工作流 {wf}** 继续。")
    return "\n".join(lines)


def injection_gate_pending_hint(*, score: str) -> str:
    return (
        f"入站消息安全评分 {score} 偏高，等待 Owner 确认。\n"
        "回复 **确认** 后请**重发上一条消息**，或 **取消** 忽略。"
    )


def workflow_gate_confirmed_hint(
    *, workflow: str, auto_resumed: bool, step_id: str = ""
) -> str:
    wf = str(workflow or "").strip() or "工作流"
    step = f"「{step_id}」" if step_id else ""
    if auto_resumed:
        return f"已确认工作流「{wf}」步骤{step}，正在自动续跑…"
    return (
        f"已确认工作流「{wf}」步骤{step}。\n"
        f"下一步：发送 **/工作流 {wf}** 继续执行。"
    )


def injection_gate_confirmed_hint(*, score: str) -> str:
    return (
        f"已确认入站安全评分 {score}。\n"
        "下一步：请**重新发送**上一条消息以继续处理。"
    )


__all__ = [
    "injection_gate_confirmed_hint",
    "injection_gate_pending_hint",
    "workflow_gate_confirmed_hint",
    "workflow_gate_pending_hint",
]
