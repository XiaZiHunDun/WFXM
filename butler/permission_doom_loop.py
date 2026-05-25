"""Doom-loop ask mode integration with session approval cache."""

from __future__ import annotations

from typing import Any, Mapping

from butler.permission_approvals import ApprovalRequest, is_approved, save_pending
from butler.tool_guardrails import GuardrailDecision, ToolCallSignature


def doom_loop_approval_request(
    tool_name: str,
    args: Mapping[str, Any] | None,
) -> ApprovalRequest:
    sig = ToolCallSignature.from_call(tool_name, args)
    return ApprovalRequest(
        permission="doom_loop",
        tool=tool_name,
        pattern=sig.args_hash[:16],
        reason="doom_loop",
    )


def check_doom_loop_ask(
    decision: GuardrailDecision,
    tool_name: str,
    args: Mapping[str, Any] | None,
) -> str | None:
    """
    Return error message when ask-mode doom loop is not approved; None if allowed.
    """
    if decision.code != "doom_loop" or decision.action != "ask":
        return None
    try:
        from butler.execution_context import get_current_session_key

        session_key = str(get_current_session_key() or "").strip()
    except Exception:
        session_key = ""
    if not session_key:
        return decision.message
    req = doom_loop_approval_request(tool_name, args)
    if is_approved(session_key, req):
        return None
    save_pending(session_key, req)
    return decision.message
