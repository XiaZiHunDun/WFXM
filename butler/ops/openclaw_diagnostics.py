"""OpenClaw-aligned diagnostic lines for /诊断."""

from __future__ import annotations

from typing import Any


def format_openclaw_diagnostic_lines(
    health: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    """Preemptive compact, tool-loop detectors, gateway admission."""
    h = health or {}
    loop = h.get("loop") if isinstance(h.get("loop"), dict) else {}
    lines: list[str] = []

    preempt_est = h.get("preemptive_estimated_tokens") or loop.get("preemptive_estimated_tokens")
    if preempt_est is not None:
        thresh = h.get("preemptive_threshold_tokens") or loop.get("preemptive_threshold_tokens")
        lines.append(f"前置压缩估算: ~{preempt_est} tok / 阈值 {thresh or '-'}")
    if h.get("preemptive_compact_applied") or loop.get("preemptive_compact_applied"):
        after = h.get("preemptive_tokens_after_compact") or loop.get("preemptive_tokens_after_compact")
        lines.append(f"前置压缩: 已执行 (压缩后 ~{after or '?'} tok)")
    if h.get("preemptive_truncate_applied") or loop.get("preemptive_truncate_applied"):
        lines.append("前置压缩: 已截断 tool 结果")
    if h.get("preemptive_overflow_fail") or loop.get("preemptive_overflow_fail"):
        msg = h.get("preemptive_overflow_message") or loop.get("preemptive_overflow_message") or ""
        lines.append(f"前置压缩: 溢出阻断 ({str(msg)[:120]})")

    try:
        from butler.core.preemptive_compact import preemptive_compact_enabled

        lines.append(
            f"前置压缩开关: {'开' if preemptive_compact_enabled() else '关'} (BUTLER_PREEMPTIVE_COMPACT)"
        )
    except Exception:
        pass

    try:
        from butler.core.tool_loop_detect import enabled_detectors, get_tool_loop_detector

        detectors = enabled_detectors()
        if detectors:
            last = get_tool_loop_detector().last_detector_label()
            lines.append(
                f"工具环检测: {','.join(sorted(detectors))}"
                + (f" (上轮触发: {last})" if last else "")
            )
        else:
            lines.append("工具环检测: 关闭")
    except Exception:
        lines.append("工具环检测: 不可用")

    try:
        from butler.gateway.reply_admission import is_admitted, reply_admission_enabled

        if reply_admission_enabled():
            sk = str(session_key or h.get("session_key") or "").strip()
            if sk and is_admitted(sk):
                lines.append("Reply 准入: 本 session 有活跃 turn")
    except Exception:
        pass

    try:
        from butler.gateway.bot_loop_guard import bot_loop_guard_enabled

        lines.append(
            f"Bot 环防护: {'开' if bot_loop_guard_enabled() else '关'} (BUTLER_BOT_LOOP_GUARD)"
        )
    except Exception:
        pass

    try:
        from butler.tools.terminal_approval import approval_required

        if approval_required():
            lines.append("Terminal 批准: 需 Owner /批准执行")
    except Exception:
        pass

    try:
        from butler.config_secrets import secrets_status_line

        lines.append(secrets_status_line())
    except Exception:
        pass

    try:
        from butler.tools.terminal_danger import danger_patterns_enabled
        from butler.tools.terminal_pattern_approval import smart_pattern_approve_enabled

        if danger_patterns_enabled():
            flag = "开" if smart_pattern_approve_enabled() else "关"
            lines.append(f"Terminal 危险模式: 开 (smart_approve={flag})")
    except Exception:
        pass

    loop_tools = loop.get("tool_selector_output") or h.get("tool_selector_output")
    if loop_tools is not None:
        dropped = loop.get("tool_selector_dropped") or h.get("tool_selector_dropped") or 0
        lines.append(f"工具预选: 出站 {loop_tools} 工具 (省略 {dropped})")

    return lines
