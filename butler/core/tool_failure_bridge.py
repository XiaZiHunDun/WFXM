"""Integration of ToolFailure/ToolSuccess with tool execution pipeline.

Provides conversion functions between raw tool results and the
ToolFailure/ToolSuccess types used with the Result monad.
"""

from __future__ import annotations

import json
import logging

from butler.core.effects.tool_failure import (
    ToolFailure,
    ToolSuccess,
    tool_failure,
    tool_success,
)

logger = logging.getLogger(__name__)


def classify_tool_error(result: str) -> tuple[bool, str, str]:
    """Parse a tool result string and classify any error.

    Returns (is_error, error_message, error_kind).
    """
    is_error = False
    error_message = ""
    error_kind = "retry"

    try:
        parsed = json.loads(result) if isinstance(result, str) else result
        if isinstance(parsed, dict):
            if parsed.get("error"):
                is_error = True
                error_message = str(parsed.get("error", ""))
                error_kind = parsed.get("error_kind", "retry")
            elif parsed.get("status") == "cancelled":
                is_error = True
                error_message = str(parsed.get("error", "Cancelled"))
                error_kind = "stop"
    except (json.JSONDecodeError, TypeError):
        pass

    return is_error, error_message, error_kind


def tool_result_to_effects(
    tool_name: str,
    result: str,
    duration_ms: int = 0,
) -> ToolSuccess | ToolFailure:
    """Convert a raw tool execution result to ToolSuccess or ToolFailure.

    This bridges the traditional string-based tool results with the
    functional Effects types used in the result monad.

    Args:
        tool_name: Name of the executed tool.
        result: Raw result string from tool execution.
        duration_ms: Execution duration in milliseconds.

    Returns:
        ToolSuccess on success, ToolFailure on error.
    """
    is_error, error_message, error_kind = classify_tool_error(result)

    if is_error:
        return tool_failure(
            tool_name=tool_name,
            message=error_message or "Unknown tool error",
            kind=error_kind,
            duration_ms=duration_ms,
            raw_result=result[:500],
        )
    else:
        return tool_success(
            tool_name=tool_name,
            result=result,
            output=result[:200] if result else "",
            duration_ms=duration_ms,
        )


def create_error_tool_failure(
    tool_name: str,
    exc: Exception,
    duration_ms: int = 0,
) -> ToolFailure:
    """Create a ToolFailure from an exception.

    Provides standardized error handling for unhandled exceptions
    during tool execution.
    """
    error_kind = "retry"
    if hasattr(exc, "error_kind"):
        error_kind = getattr(exc, "error_kind", "retry")

    return tool_failure(
        tool_name=tool_name,
        message=str(exc),
        kind=error_kind,
        exc=exc,
        duration_ms=duration_ms,
        exception_type=type(exc).__name__,
    )


__all__ = [
    "classify_tool_error",
    "tool_result_to_effects",
    "create_error_tool_failure",
]
