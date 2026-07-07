"""Tool orchestration gates and fail-closed dispatch (P0-A)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort

from butler.core.confirm_flags import permission_risk_heuristic_enabled
from butler.core.approval_cards import format_terminal_pattern_card
from butler.permissions.approvals import (
    ApprovalRequest,
    save_pending,
)
from butler.tools.terminal_danger import (
    check_dangerous_command,
    set_terminal_session_context,
)
from butler.tools.terminal_approval import check_approval
from butler.hooks.runner import (
    run_permission_request_hooks,
    run_pre_tool_hooks,
)
from butler.mcp.approval import check_mcp_tool_approval
from butler.tools.network_search_policy import (
    is_firecrawl_agent_tool,
    is_firecrawl_feedback_tool,
    is_web_search_intent,
)
from butler.core.session_epoch import last_user_query_in_epoch

logger = logging.getLogger(__name__)


def _deny(code: str, message: str) -> str:
    return json.dumps({"ok": False, "error": message, "code": code}, ensure_ascii=False)


def terminal_risk_ask_safe(
    *,
    danger_pattern: str,
    command: str,
    session_key: str,
) -> str | None:
    def _run() -> str | None:

        if not (permission_risk_heuristic_enabled() and session_key):
            return None
        save_pending(
            session_key,
            ApprovalRequest(
                permission="terminal_risk",
                tool="terminal",
                pattern=danger_pattern or "danger",
                reason="dangerous command",
            ),
        )
        return _deny(
            "TERMINAL_RISK_ASK",
            format_terminal_pattern_card(danger_pattern or "danger", command_preview=command),
        )

    result = safe_best_effort(_run, label="tool_orchestrator.terminal_risk_ask", default=None)
    return result if isinstance(result, str) else None


def check_terminal_danger_safe(command: str, session_key: str) -> Any | None:
    def _run() -> Any:

        set_terminal_session_context(session_key)
        return check_dangerous_command(command)

    return safe_best_effort(_run, label="tool_orchestrator.terminal_danger", default=None)


def check_terminal_approval_safe(command: str, *, cwd: str, session_key: str) -> str | None:
    def _run() -> str | None:

        block = check_approval(command, cwd=cwd, session_key=session_key)
        return str(block) if block else None

    block = safe_best_effort(_run, label="tool_orchestrator.terminal_approval", default=None)
    return block if isinstance(block, str) and block else None


def run_mcp_pre_hooks_safe(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str,
) -> str | None:
    def _run() -> str | None:

        perm_block = run_permission_request_hooks(tool_name, args, session_key=session_key)
        if perm_block:
            return _deny("PERMISSION_REQUEST_HOOK", perm_block)
        pre_block = run_pre_tool_hooks(tool_name, args)
        if pre_block:
            return _deny("HOOK_BLOCKED", pre_block)
        return None

    result = safe_best_effort(_run, label="tool_orchestrator.mcp_pre_hooks", default=None)
    return result if isinstance(result, str) else None


def check_mcp_approval_safe(
    *,
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    session_key: str,
    classification: str,
    model_message_fn: Callable[[str, str, str], str],
) -> str | None:
    def _run() -> str | None:

        block = check_mcp_tool_approval(
            server_id=server_id,
            tool_name=tool_name,
            args=args,
            session_key=session_key,
            classification=classification,
        )
        if block:
            return _deny(
                "MCP_APPROVAL_REQUIRED",
                model_message_fn(tool_name, session_key, block),
            )
        return None

    result = safe_best_effort(_run, label="tool_orchestrator.mcp_approval", default=None)
    return result if isinstance(result, str) else None


def mcp_approval_model_message_safe(tool_name: str, session_key: str, raw: str) -> str:
    def _run() -> str:

        q = last_user_query_in_epoch(session_key) if session_key else ""
        restricted = is_firecrawl_feedback_tool(tool_name) or is_firecrawl_agent_tool(tool_name)
        if is_web_search_intent(q) or restricted:
            return (
                "该 MCP 工具在本轮已跳过。勿向用户提及审批、确认或内部流程；"
                "请基于已有 firecrawl_search / web_search 结果继续作答，"
                "每条结论附完整 https 来源 URL。"
            )
        return raw

    result = safe_best_effort(
        _run,
        label="tool_orchestrator.mcp_model_message",
        default=raw,
    )
    return result if isinstance(result, str) else raw


def run_orchestrator_pre_hooks_safe(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str,
) -> str | None:
    def _run() -> str | None:

        perm_block = run_permission_request_hooks(tool_name, args, session_key=session_key)
        if perm_block:
            return _deny("PERMISSION_REQUEST_HOOK", perm_block)
        pre_block = run_pre_tool_hooks(tool_name, args)
        if pre_block:
            return _deny("HOOK_BLOCKED", pre_block)
        return None

    result = safe_best_effort(_run, label="tool_orchestrator.pre_hooks", default=None)
    return result if isinstance(result, str) else None


def dispatch_handler_loud(
    tool_name: str,
    args: dict[str, Any],
    handler: Callable[..., str],
) -> str:
    try:
        return handler(**args)
    except Exception as exc:
        logger.error("Tool %s failed: %s", tool_name, exc)
        return _deny("TOOL_ERROR", f"Tool '{tool_name}' failed: {exc}")
