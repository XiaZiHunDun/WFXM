"""Tool execution orchestration (Codex ToolOrchestrator subset — no OS sandbox)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


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
    try:
        from butler.tools.terminal_danger import check_dangerous_command, set_terminal_session_context

        set_terminal_session_context(session_key)
        danger = check_dangerous_command(command)
        if not danger.allowed:
            try:
                from butler.core.confirm_flags import permission_risk_heuristic_enabled
                from butler.permissions.approvals import ApprovalRequest, save_pending

                if permission_risk_heuristic_enabled() and session_key:
                    save_pending(
                        session_key,
                        ApprovalRequest(
                            permission="terminal_risk",
                            tool="terminal",
                            pattern=danger.pattern or "danger",
                            reason=danger.reason,
                        ),
                    )
                    return _deny(
                        "TERMINAL_RISK_ASK",
                        (
                            f"{danger.reason}\n"
                            "（Owner：/批准执行 <命令> 或 /批准模式 "
                            f"{danger.pattern}> 后重试）"
                        ),
                    )
            except Exception as exc:
                logger.debug("run terminal with gates skipped: %s", exc)
            return _deny("TERMINAL_DANGER_PATTERN", danger.reason)
    except Exception as exc:
        logger.debug("terminal danger gate: %s", exc)

    try:
        from butler.tools.terminal_approval import check_approval

        block = check_approval(command, cwd=cwd, session_key=session_key)
        if block:
            return _deny("TERMINAL_APPROVAL_REQUIRED", block)
    except Exception as exc:
        logger.debug("terminal approval gate: %s", exc)

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
    try:
        from butler.hooks.runner import run_permission_request_hooks, run_pre_tool_hooks

        perm_block = run_permission_request_hooks(
            tool_name,
            args,
            session_key=session_key,
        )
        if perm_block:
            return _deny("PERMISSION_REQUEST_HOOK", perm_block)

        pre_block = run_pre_tool_hooks(tool_name, args)
        if pre_block:
            return _deny("HOOK_BLOCKED", pre_block)
    except Exception as exc:
        logger.debug("mcp pre-hooks: %s", exc)

    try:
        from butler.mcp.approval import check_mcp_tool_approval

        block = check_mcp_tool_approval(
            server_id=server_id,
            tool_name=tool_name,
            args=args,
            session_key=session_key,
            classification=classification,
        )
        if block:
            return _deny("MCP_APPROVAL_REQUIRED", block)
    except Exception as exc:
        logger.debug("mcp approval gate: %s", exc)
    return run_fn()


def dispatch_with_orchestrator(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str = "",
    handler: Callable[..., str],
) -> str:
    """Hooks + PermissionRequest + handler for generic registry tools."""
    try:
        from butler.hooks.runner import run_permission_request_hooks, run_pre_tool_hooks

        perm_block = run_permission_request_hooks(
            tool_name,
            args,
            session_key=session_key,
        )
        if perm_block:
            return _deny("PERMISSION_REQUEST_HOOK", perm_block)

        pre_block = run_pre_tool_hooks(tool_name, args)
        if pre_block:
            return _deny("HOOK_BLOCKED", pre_block)
    except Exception as exc:
        logger.debug("orchestrator pre-hooks: %s", exc)

    try:
        return handler(**args)
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc)
        return _deny("TOOL_ERROR", f"Tool '{tool_name}' failed: {exc}")


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
