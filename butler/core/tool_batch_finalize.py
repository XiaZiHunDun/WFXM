"""Tool result finalization extracted from ``tool_batch`` (P1-C)."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable, cast

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def dispatch_tool_with_envelope(
    tool_dispatcher: Callable[[str, dict[str, Any]], str] | None,
    name: str,
    args: dict[str, Any],
) -> str:
    """Dispatch through the configured handler and normalize failures."""
    if tool_dispatcher:
        try:
            result = tool_dispatcher(name, args)
            return finalize_unenveloped_failure_result(name, args, result)
        except Exception as exc:
            logger.error("Tool %s failed: %s", name, exc)
            return finalize_fallback_tool_result(
                name,
                args,
                {
                    "error": f"Tool execution failed: {exc}",
                    "code": "TOOL_DISPATCH_ERROR",
                },
            )
    return finalize_fallback_tool_result(
        name,
        args,
        {
            "error": f"No tool dispatcher configured, cannot run '{name}'",
            "code": "TOOL_DISPATCH_ERROR",
        },
    )


def finalize_fallback_tool_result(name: str, args: dict[str, Any], result: Any) -> str:
    from butler.tools.registry import finalize_tool_result

    return cast(str, finalize_tool_result(name, args, result))


def finalize_guardrail_halt_result(
    name: str,
    args: dict[str, Any],
    result: str,
    decision: Any,
) -> str:
    from butler.tools.registry import finalize_tool_result, pop_last_tool_audit_for_tool

    pop_last_tool_audit_for_tool(name)
    payload = parse_tool_result_object(result)
    if payload is None:
        payload = {"error": result or decision.message}
    else:
        payload = dict(payload)
    for key in ("ok", "tool", "code"):
        payload.pop(key, None)
    payload["error"] = decision.message
    payload["guardrail"] = {
        "action": decision.action,
        "code": decision.code,
        "count": decision.count,
    }
    return cast(str, finalize_tool_result(name, args, payload))


def finalize_unenveloped_failure_result(name: str, args: dict[str, Any], result: str) -> str:
    payload = parse_tool_result_object(result)
    if not isinstance(payload, dict):

        def _preview() -> str:
            from butler.tools.registry import finalize_tool_result

            return cast(str, finalize_tool_result(
                name,
                args,
                {"preview": str(result)[:200]},
            ))

        preview = safe_best_effort(_preview, label="tool_batch.finalize_preview")
        if preview is not None:
            return cast(str, preview)
        return result
    if payload.get("ok") is False and payload.get("tool") and payload.get("code"):
        return result
    failed = (
        "error" in payload
        or payload.get("success") is False
        or (isinstance(payload.get("exit_code"), int) and payload["exit_code"] != 0)
    )
    if failed:
        payload = dict(payload)
        payload.setdefault("code", "TOOL_ERROR")
        return finalize_fallback_tool_result(name, args, payload)
    return result


def parse_tool_result_object(result: Any) -> dict[str, Any] | None:
    if isinstance(result, dict):
        return result
    if not isinstance(result, str):
        return None
    try:
        parsed = json.loads(result)
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    return parsed if isinstance(parsed, dict) else None


__all__ = [
    "dispatch_tool_with_envelope",
    "finalize_fallback_tool_result",
    "finalize_guardrail_halt_result",
    "finalize_unenveloped_failure_result",
    "parse_tool_result_object",
]
