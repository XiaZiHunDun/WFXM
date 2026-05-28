"""MCP tool approval templates and session persist (Codex mcp_tool_call subset)."""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def mcp_approval_enabled() -> bool:
    return env_truthy("BUTLER_MCP_APPROVAL", default=True)


def mcp_tool_fingerprint(server_id: str, tool_name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(
        {
            "server_id": str(server_id or ""),
            "tool": str(tool_name or ""),
            "args": args if isinstance(args, dict) else {},
        },
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def format_mcp_approval_message(
    *,
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    classification: str = "",
    connector_name: str = "",
) -> str:
    """Human-readable block for WeChat / pending approval."""
    lines = [
        "MCP 工具需确认",
        f"  server: {server_id or '?'}",
        f"  tool: {tool_name}",
    ]
    if connector_name:
        lines.append(f"  connector: {connector_name}")
    if classification:
        lines.append(f"  类型: {classification}")
    preview = json.dumps(args, ensure_ascii=False, default=str)[:400]
    if preview:
        lines.append(f"  参数: {preview}")
    lines.append("  回复 /批准一次 或 /始终允许 mcp_tool")
    return "\n".join(lines)


def check_mcp_tool_approval(
    *,
    server_id: str,
    tool_name: str,
    args: dict[str, Any],
    session_key: str,
    classification: str = "",
) -> str | None:
    """
    Return error message if MCP call blocked pending approval; None if allowed.
    """
    if not mcp_approval_enabled():
        return None
    sk = str(session_key or "").strip()
    if not sk:
        return None

    from butler.mcp.classify import is_mutating_classification

    if not is_mutating_classification(classification):
        return None

    from butler.permissions.approvals import ApprovalRequest, is_approved, save_pending

    fp = mcp_tool_fingerprint(server_id, tool_name, args)
    req = ApprovalRequest(
        permission="mcp_tool",
        tool=tool_name,
        pattern=fp,
        reason=format_mcp_approval_message(
            server_id=server_id,
            tool_name=tool_name,
            args=args,
            classification=classification,
        ),
    )
    if is_approved(sk, req):
        return None

    save_pending(sk, req)
    return req.reason or "MCP 工具需 Owner 批准（/批准一次）"


def grant_mcp_session_always(session_key: str, server_id: str = "*") -> str:
    """Grant always-allow for mcp_tool permission scoped to server pattern."""
    from butler.permissions.approvals import grant_always

    return grant_always(
        session_key,
        permission="mcp_tool",
        tool="*",
        pattern=str(server_id or "*"),
    )


__all__ = [
    "check_mcp_tool_approval",
    "format_mcp_approval_message",
    "grant_mcp_session_always",
    "mcp_approval_enabled",
    "mcp_tool_fingerprint",
]
