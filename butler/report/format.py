"""Helpers for channel-specific report formatting."""

from __future__ import annotations

from butler.core.loop_types import LoopResult, LoopStatus
from butler.report.generator import format_for_wechat, get_last_report


# Sprint 28 P1-3.4: /详细 --child <child_sk> 解析.
#   支持 `--child foo` 与 `--child=foo` 两种形式; 缺值 / 缺 sk 视为无效
#   (返回 (原 arg, None) 让上层走旧路径, 不静默吞).
_CHILD_FLAG_SPACE = "--child "
_CHILD_FLAG_EQ = "--child="


def parse_child_arg(arg: str) -> tuple[str, str | None]:
    """Return (remaining_arg, child_sk_or_None) from a /详细 argv string.

    Forms handled:
      - ``--child <sk>``        → (``""``, ``<sk>``)
      - ``--child=<sk>``        → (``""``, ``<sk>``)
      - ``--child <sk> <rest>`` → (``<rest>``, ``<sk>``)
      - ``--child=<sk> <rest>`` → (``<rest>``, ``<sk>``)
      - anything else           → (``<arg>``, ``None``)  (旧路径不变)
    """
    s = str(arg or "").strip()
    if not s:
        return "", None
    if s == "--child":
        return s, None
    if s.startswith(_CHILD_FLAG_EQ):
        rest = s[len(_CHILD_FLAG_EQ):].strip()
        if not rest:
            return s, None
        parts = rest.split(maxsplit=1)
        child = parts[0].strip()
        if not child:
            return s, None
        remaining = parts[1].strip() if len(parts) > 1 else ""
        return remaining, child
    if s.startswith(_CHILD_FLAG_SPACE):
        rest = s[len(_CHILD_FLAG_SPACE):].strip()
        if not rest:
            return s, None
        parts = rest.split(maxsplit=1)
        child = parts[0].strip()
        if not child:
            return s, None
        remaining = parts[1].strip() if len(parts) > 1 else ""
        return remaining, child
    return s, None


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
    from butler.execution_context import get_current_session_key

    if result.status == LoopStatus.WAITING_CONFIRMATION:
        text = (result.final_response or "").strip()
        return text or "等待您确认高风险工具。回复 /确认工具 执行。"
    if result.status == LoopStatus.STUCK:
        text = (result.final_response or "").strip()
        prefix = "任务卡住："
        body = text or "工具循环检测触发，请调整策略或发 /详细 查看。"
        return f"{prefix}{body}"[:max_length]

    report = get_last_report(get_current_session_key())
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


def format_child_session_detail(child_sk: str, *, max_lines: int = 80) -> str:
    """Render a child session transcript as a markdown summary for /详细.

    Sprint 28 P1-3.4: 给 /详细 --child <child_sk> 用的渲染函数. 直接走
    ``build_session_markdown`` (80 行) + 头注 (子 session key + 父反查提示).

    Fallback (按优先级, 都返回友好中文提示):
      1. transcript 关闭 (BUTLER_SESSION_TRANSCRIPT=0)
      2. child_sk 无对应 transcript.jsonl (未创建 / 已清理)
    """
    sk = str(child_sk or "").strip()
    if not sk:
        return "未提供 child_session_key; 语法: /详细 --child <child_sk>"
    try:
        from butler.core.session_transcript import transcript_enabled

        if not transcript_enabled():
            return (
                f"child_session: {sk}\n"
                "Transcript: 已关闭 (BUTLER_SESSION_TRANSCRIPT=0)\n"
                "提示: 设置环境变量后重发 /详细 --child <sk> 查看子会话"
            )
        from butler.core.transcript_export import build_session_markdown

        body = build_session_markdown(sk, max_lines=max_lines, include_tasks=False)
        if "无 transcript 记录" in body or "BUTLER_SESSION_TRANSCRIPT" in body:
            return (
                f"child_session: {sk}\n"
                "Transcript: 暂无记录 (子会话可能尚未产生事件, 或 jsonl 已被 retention 清掉)\n"
                "提示: 父会话 /任务 行会显示 child_sk; 发 /任务 --task-id <tid> 可反查"
            )
        return f"child_session: {sk}\n\n{body}"
    except Exception as exc:  # pragma: no cover — 容错, 永不抛给 UI
        return (
            f"child_session: {sk}\n"
            f"渲染失败: {str(exc)[:200]}\n"
            "提示: 检查 transcript.jsonl 是否可读, 或联系 owner"
        )


__all__ = [
    "parse_child_arg",
    "parse_detail_section",
    "format_child_session_detail",
    "turn_used_delegate_task",
    "wechat_response_text",
]
