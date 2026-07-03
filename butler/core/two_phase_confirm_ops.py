"""Two-phase confirm best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def terminal_command_blocked_safe(command: str) -> bool | None:
    cmd = str(command or "").strip()
    if not cmd:
        return None

    def _run() -> bool:
        from butler.tools.terminal_danger import check_dangerous_command

        danger = check_dangerous_command(cmd)
        return not danger.allowed

    result = safe_best_effort(
        _run,
        label="two_phase_confirm.terminal_danger",
        default=None,
    )
    if result is None:
        return None
    return bool(result)


def resolve_session_key_safe(session_key: str) -> str:
    key = str(session_key or "").strip()
    if key:
        return key

    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip() or "default"

    result = safe_best_effort(
        _run,
        label="two_phase_confirm.session_key",
        default="default",
    )
    return str(result or "default")


def record_two_phase_wait_safe(session_key: str, tool_name: str) -> None:
    def _run() -> None:
        from butler.core.session_transcript import record_workflow_step

        record_workflow_step(
            session_key,
            workflow="two_phase",
            step_id=tool_name,
            phase="waiting_confirmation",
            step_index=1,
            step_total=1,
        )

    safe_best_effort(_run, label="two_phase_confirm.record_wait", default=None)


def dispatch_pending_tool_loud(tool_name: str, args: dict[str, Any]) -> tuple[str | None, str | None]:
    try:
        from butler.tools.registry import dispatch_tool

        result = dispatch_tool(tool_name, args)
        return str(result or ""), None
    except Exception as exc:
        logger.warning("pending tool dispatch failed: %s", exc)
        return None, str(exc)
