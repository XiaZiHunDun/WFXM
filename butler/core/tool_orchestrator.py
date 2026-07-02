"""Tool execution orchestration (Codex ToolOrchestrator subset; optional Linux bubblewrap)."""

from __future__ import annotations

import json
from typing import Any, Callable


def _deny(code: str, message: str) -> str:
    return json.dumps({"ok": False, "error": message, "code": code}, ensure_ascii=False)


def run_terminal_with_gates(
    command: str,
    *,
    cwd: str = "",
    session_key: str = "",
    run_fn: Callable[[], str],
) -> str:
    """Policy → danger → approval → execpolicy path for terminal."""
    from butler.core.approval_cards import format_terminal_pattern_card
    from butler.core.tool_orchestrator_ops import (
        check_terminal_approval_safe,
        check_terminal_danger_safe,
        terminal_risk_ask_safe,
    )

    danger = check_terminal_danger_safe(command, session_key)
    if danger is not None and not danger.allowed:
        risk = terminal_risk_ask_safe(
            danger_pattern=danger.pattern or "danger",
            command=command,
            session_key=session_key,
        )
        if risk:
            return risk
        return _deny(
            "TERMINAL_DANGER_PATTERN",
            format_terminal_pattern_card(
                danger.pattern or "danger",
                command_preview=command,
            )
            if danger.pattern
            else danger.reason,
        )

    block = check_terminal_approval_safe(command, cwd=cwd, session_key=session_key)
    if block:
        from butler.core.approval_cards import format_terminal_approval_message

        return _deny("TERMINAL_APPROVAL_REQUIRED", format_terminal_approval_message(command, block))

    return run_fn()


def run_mcp_with_gates(
    *,
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    session_key: str,
    classification: str,
    run_fn: Callable[[], str],
) -> str:
    from butler.core.tool_orchestrator_ops import (
        check_mcp_approval_safe,
        mcp_approval_model_message_safe,
        run_mcp_pre_hooks_safe,
    )

    pre = run_mcp_pre_hooks_safe(tool_name, args, session_key=session_key)
    if pre:
        return pre

    block = check_mcp_approval_safe(
        server_id=server_id,
        tool_name=tool_name,
        args=args,
        session_key=session_key,
        classification=classification,
        model_message_fn=mcp_approval_model_message_safe,
    )
    if block:
        return block
    return run_fn()


def _mcp_approval_model_message(tool_name: str, session_key: str, raw: str) -> str:
    from butler.core.tool_orchestrator_ops import mcp_approval_model_message_safe

    return mcp_approval_model_message_safe(tool_name, session_key, raw)


def dispatch_with_orchestrator(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str = "",
    handler: Callable[..., str],
) -> str:
    """Hooks + PermissionRequest + handler for generic registry tools."""
    from butler.core.tool_orchestrator_ops import (
        dispatch_handler_loud,
        run_orchestrator_pre_hooks_safe,
    )

    pre = run_orchestrator_pre_hooks_safe(tool_name, args, session_key=session_key)
    if pre:
        return pre
    return dispatch_handler_loud(tool_name, args, handler)


def run_with_approval_gate(
    *,
    tool_name: str,
    run_fn: Callable[[], str],
    approval_fn: Callable[[], str | None] | None = None,
) -> str:
    """Minimal gate: optional approval_fn returns error message to block."""
    if approval_fn is not None:
        block = approval_fn()
        if block:
            return _deny("APPROVAL_REQUIRED", block)
    return run_fn()


__all__ = [
    "dispatch_with_orchestrator",
    "run_mcp_with_gates",
    "run_terminal_with_gates",
    "run_with_approval_gate",
]
