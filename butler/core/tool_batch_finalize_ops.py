"""Fail-closed tool dispatch envelope helper (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Callable

logger = logging.getLogger(__name__)


def dispatch_tool_with_envelope_loud(
    tool_dispatcher: Callable[[str, dict[str, Any]], str],
    name: str,
    args: dict[str, Any],
) -> str:
    from butler.core.tool_batch_finalize import (
        finalize_fallback_tool_result,
        finalize_unenveloped_failure_result,
    )

    try:
        result = tool_dispatcher(name, args)
        return str(finalize_unenveloped_failure_result(name, args, result))
    except Exception as exc:
        logger.error("Tool %s failed: %s", name, exc)
        return str(
            finalize_fallback_tool_result(
                name,
                args,
                {
                    "error": f"Tool execution failed: {exc}",
                    "code": "TOOL_DISPATCH_ERROR",
                },
            )
        )
