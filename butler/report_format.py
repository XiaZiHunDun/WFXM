"""Helpers for channel-specific report formatting."""

from __future__ import annotations

from butler.core.loop_types import LoopResult
from butler.report import format_for_wechat, get_last_report


def turn_used_delegate_task(result: LoopResult) -> bool:
    """True if this loop turn invoked ``delegate_task``."""
    for msg in getattr(result, "messages", []) or []:
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        for tc in msg.get("tool_calls") or []:
            if not isinstance(tc, dict):
                continue
            fn = tc.get("function") if isinstance(tc.get("function"), dict) else {}
            name = fn.get("name") or tc.get("name") or ""
            if name == "delegate_task":
                return True
    return False


def wechat_response_text(
    result: LoopResult,
    *,
    max_length: int = 2000,
) -> str:
    """Pick compact delegate report or plain assistant text for WeChat."""
    report = get_last_report()
    if report and turn_used_delegate_task(result):
        text = format_for_wechat(report)
    elif result.final_response:
        text = result.final_response
    else:
        text = "（执行完成，无文字输出）"

    if len(text) > max_length:
        return text[: max_length - 3] + "..."
    return text


def parse_detail_section(arg: str) -> str:
    """Map user arg to ``format_detail`` section id."""
    key = (arg or "").strip().lower()
    if not key:
        return ""
    if key in {"changes", "change", "files", "file", "变更", "文件"}:
        return "changes"
    if key in {"decisions", "decision", "决策"}:
        return "decisions"
    if key in {"issues", "issue", "risk", "问题", "风险"}:
        return "issues"
    if key in {"log", "steps", "步骤", "日志"}:
        return ""
    return key


__all__ = [
    "parse_detail_section",
    "turn_used_delegate_task",
    "wechat_response_text",
]
