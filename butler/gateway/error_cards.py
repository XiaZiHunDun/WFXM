"""Structured error messages for WeChat — doom_loop, permission, timeout."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def format_error_card(event_type: str, **kwargs) -> str | None:
    """Return a structured WeChat error notification, or None if not applicable."""
    if event_type == "doom_loop":
        tool = kwargs.get("tool", "unknown")
        count = kwargs.get("count", 0)
        return (
            f"[拦截] 检测到重复操作: {tool}（已连续 {count} 次）\n"
            "可发 /批准一次 放行，或 /始终允许 doom_loop 解除限制"
        )

    if event_type == "permission_deny":
        tool = kwargs.get("tool", "unknown")
        reason = kwargs.get("reason", "")
        return (
            f"[权限] {tool} 被拒绝\n"
            f"原因: {reason}\n"
            "可发 /批准执行 或 /批准一次 放行"
        )

    if event_type == "delegate_timeout":
        role = kwargs.get("role", "unknown")
        elapsed = kwargs.get("elapsed", 0)
        return (
            f"[超时] 委派 {role} 已运行 {elapsed}s\n"
            "可发 /health 查看状态，或 /停止 中断"
        )

    if event_type == "tool_error":
        tool = kwargs.get("tool", "unknown")
        error = kwargs.get("error", "")
        return (
            f"[错误] {tool} 执行失败\n"
            f"{error[:200]}\n"
            "可发 /详细 查看完整信息"
        )

    return None
