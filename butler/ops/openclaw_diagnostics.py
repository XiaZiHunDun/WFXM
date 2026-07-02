"""OpenClaw-aligned diagnostic lines for /诊断."""

from __future__ import annotations

from typing import Any


def format_openclaw_diagnostic_lines(
    health: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    """Preemptive compact, tool-loop detectors, gateway admission."""
    from butler.ops.openclaw_diagnostics_ops import (
        append_bot_loop_guard_line,
        append_preemptive_compact_line,
        append_reply_admission_line,
        append_secrets_status_line,
        append_terminal_approval_line,
        append_terminal_danger_line,
        append_tool_loop_detector_line,
        extend_terminal_sandbox_lines,
    )

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

    append_preemptive_compact_line(lines)
    append_tool_loop_detector_line(lines)
    append_reply_admission_line(lines, session_key=session_key, health=h)
    append_bot_loop_guard_line(lines)
    append_terminal_approval_line(lines)
    append_secrets_status_line(lines)
    append_terminal_danger_line(lines)
    extend_terminal_sandbox_lines(lines)

    loop_tools = loop.get("tool_selector_output") or h.get("tool_selector_output")
    if loop_tools is not None:
        dropped = loop.get("tool_selector_dropped") or h.get("tool_selector_dropped") or 0
        lines.append(f"工具预选: 出站 {loop_tools} 工具 (省略 {dropped})")

    return lines
