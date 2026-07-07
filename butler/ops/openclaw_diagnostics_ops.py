"""OpenClaw diagnostic probe helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


from butler.core.preemptive_compact import preemptive_compact_enabled
from butler.core.tool_loop_detect import (
    enabled_detectors,
    get_tool_loop_detector,
)
from butler.gateway.reply_admission import (
    is_admitted,
    reply_admission_enabled,
)
from butler.gateway.bot_loop_guard import bot_loop_guard_enabled
from butler.tools.terminal_approval import approval_required
from butler.config_secrets import secrets_status_line
from butler.tools.terminal_danger import danger_patterns_enabled
from butler.tools.terminal_pattern_approval import smart_pattern_approve_enabled
from butler.ops.terminal_sandbox_diagnostics import format_terminal_sandbox_diagnostic_lines
from butler.tools.path_safety import current_workspace_root

def append_preemptive_compact_line(lines: list[str]) -> None:
    def _run() -> None:

        lines.append(
            f"前置压缩开关: {'开' if preemptive_compact_enabled() else '关'} (BUTLER_PREEMPTIVE_COMPACT)"
        )

    safe_best_effort(_run, label="openclaw_diagnostics.preemptive", default=None)


def append_tool_loop_detector_line(lines: list[str]) -> None:
    def _run() -> None:

        detectors = enabled_detectors()
        if detectors:
            last = get_tool_loop_detector().last_detector_label()
            lines.append(
                f"工具环检测: {','.join(sorted(detectors))}"
                + (f" (上轮触发: {last})" if last else "")
            )
        else:
            lines.append("工具环检测: 关闭")

    result = safe_best_effort(_run, label="openclaw_diagnostics.tool_loop", default=False)
    if result is False:
        lines.append("工具环检测: 不可用")


def append_reply_admission_line(
    lines: list[str],
    *,
    session_key: str,
    health: dict[str, Any],
) -> None:
    def _run() -> None:

        if reply_admission_enabled():
            sk = str(session_key or health.get("session_key") or "").strip()
            if sk and is_admitted(sk):
                lines.append("Reply 准入: 本 session 有活跃 turn")

    safe_best_effort(_run, label="openclaw_diagnostics.reply_admission", default=None)


def append_bot_loop_guard_line(lines: list[str]) -> None:
    def _run() -> None:

        lines.append(
            f"Bot 环防护: {'开' if bot_loop_guard_enabled() else '关'} (BUTLER_BOT_LOOP_GUARD)"
        )

    safe_best_effort(_run, label="openclaw_diagnostics.bot_loop_guard", default=None)


def append_terminal_approval_line(lines: list[str]) -> None:
    def _run() -> None:

        if approval_required():
            lines.append("Terminal 批准: 需 Owner /批准执行")

    safe_best_effort(_run, label="openclaw_diagnostics.terminal_approval", default=None)


def append_secrets_status_line(lines: list[str]) -> None:
    def _run() -> None:

        lines.append(secrets_status_line())

    safe_best_effort(_run, label="openclaw_diagnostics.secrets", default=None)


def append_terminal_danger_line(lines: list[str]) -> None:
    def _run() -> None:

        if danger_patterns_enabled():
            flag = "开" if smart_pattern_approve_enabled() else "关"
            lines.append(f"Terminal 危险模式: 开 (smart_approve={flag})")

    safe_best_effort(_run, label="openclaw_diagnostics.terminal_danger", default=None)


def extend_terminal_sandbox_lines(lines: list[str]) -> None:
    def _run() -> None:

        ws = current_workspace_root()
        lines.extend(format_terminal_sandbox_diagnostic_lines(workspace=ws))

    safe_best_effort(_run, label="openclaw_diagnostics.terminal_sandbox", default=None)
