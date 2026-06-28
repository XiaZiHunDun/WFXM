"""Owner approval card formatters (ENG-7 — core/tools layer, no gateway import)."""

from __future__ import annotations


def format_approval_card(
    *,
    title: str = "需要您批准",
    reason: str,
    approve_command: str = "",
    extra: str = "",
) -> str:
    """Return a consistent approval block for Owner-facing denials."""
    lines = [f"【{title}】", f"原因：{reason.strip()}"]
    if approve_command.strip():
        lines.append("操作：复制整行发送")
        lines.append(approve_command.strip())
    if extra.strip():
        lines.append(extra.strip())
    return "\n".join(lines)


def is_approval_card(text: str) -> bool:
    return (text or "").strip().startswith("【")


def format_terminal_exec_card(command: str, *, reason: str = "终端命令需 Owner 确认") -> str:
    cmd = (command or "").strip()
    preview = cmd[:200] + ("…" if len(cmd) > 200 else "")
    return format_approval_card(
        reason=reason,
        approve_command=f"/批准执行 {preview}",
        extra="批准后 5 分钟内可重试同一命令。",
    )


def format_terminal_approval_message(command: str, block: str) -> str:
    """Return ``block`` if already a card; else wrap as exec approval card."""
    msg = (block or "").strip()
    if is_approval_card(msg):
        return msg
    return format_terminal_exec_card(command, reason=msg or "终端命令需 Owner 确认")


def format_terminal_sandbox_card(command: str, *, constraint: str = "") -> str:
    cmd = (command or "").strip()
    preview = cmd[:120] + ("…" if len(cmd) > 120 else "")
    reason = "沙箱内无法完成（"
    reason += constraint or "权限或网络受限"
    reason += "）"
    return format_approval_card(
        reason=reason,
        approve_command=f"/批准沙箱外 {preview}",
        extra="仅在确有必要时使用；跳过后将无 OS 沙箱保护。",
    )


def format_terminal_pattern_card(pattern: str, *, command_preview: str = "") -> str:
    pat = (pattern or "").strip()
    reason = "命令命中危险模式，已阻断"
    if command_preview.strip():
        reason += f"（{command_preview.strip()[:80]}）"
    return format_approval_card(
        reason=reason,
        approve_command=f"/批准模式 {pat}",
        extra="或逐条批准：/批准执行 <完整命令>",
    )


def format_permission_once_card(*, fingerprint: str = "", tool: str = "") -> str:
    reason = f"{tool} 被拒绝" if tool else "操作被拒绝"
    extra = ""
    cmd = ""
    if fingerprint.strip():
        cmd = f"/批准一次 {fingerprint.strip()[:32]}"
        extra = "放行一次后请重试原操作。"
    else:
        extra = "可发 /批准一次 <指纹> 或 /始终允许 <权限>"
    return format_approval_card(reason=reason, approve_command=cmd, extra=extra)


def format_runtime_job_card(job_id: str) -> str:
    jid = (job_id or "").strip()
    return format_approval_card(
        reason="改盘类定时任务需 Owner 确认",
        approve_command=f"/批准运行 {jid}" if jid else "/批准运行 <任务id>",
    )


def format_memory_pending_card(count: int = 0) -> str:
    reason = f"有 {count} 条记忆待您确认" if count else "记忆写入需 Owner 确认"
    return format_approval_card(
        title="记忆待审",
        reason=reason,
        approve_command="/记忆待审",
        extra="查看后可用 /批准记忆 或 /拒绝记忆",
    )


__all__ = [
    "format_approval_card",
    "format_memory_pending_card",
    "format_permission_once_card",
    "format_runtime_job_card",
    "format_terminal_approval_message",
    "format_terminal_exec_card",
    "format_terminal_pattern_card",
    "format_terminal_sandbox_card",
    "is_approval_card",
]
