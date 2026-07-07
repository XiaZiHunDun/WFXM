"""Registered tool handler invocation with error envelope (P0-A / P2-F)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def invoke_registered_tool_handler(
    *,
    name: str,
    args: dict[str, Any],
    call_args: dict[str, Any],
    handler: Any,
    started_at: float,
    finalize_result: Callable[..., str],
    apply_hooks: Callable[..., str],
) -> str:
    try:
        from butler.tools.tool_implicit_context import merge_implicit_tool_args

        merged = merge_implicit_tool_args(call_args)
        result = handler(**merged)
        if name == "web_search":
            from butler.tools.registry_gates import note_web_search_outcome

            note_web_search_outcome(result)
        return apply_hooks(
            name,
            args,
            finalize_result(name, args, result, started_at=started_at),
        )
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        from butler.tools.registry_gates import tool_error_payload

        payload = tool_error_payload(name, exc)
        err_result = finalize_result(
            name,
            args,
            payload,
            started_at=started_at,
        )
        return apply_hooks(name, args, err_result, failed=True)
