"""Integration between tool execution and event system.

Provides functions to emit session events during tool execution,
enabling event sourcing for session state management.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def emit_tool_called_event(
    session_id: str,
    tool_name: str,
    call_id: str,
    turn_number: int = 0,
    args: dict[str, Any] | None = None,
) -> None:
    """Emit a ToolCalled event to the event bus.

    Called when a tool execution starts.
    """
    try:
        from butler.core.events import create_tool_called, get_global_event_bus

        args_preview = ""
        if args:
            try:
                args_preview = json.dumps(args, ensure_ascii=False)[:200]
            except (TypeError, ValueError):
                args_preview = str(args)[:200]

        event = create_tool_called(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            turn_number=turn_number,
            args_preview=args_preview,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug("Emitted ToolCalled event: %s (call_id=%s)", tool_name, call_id)
    except Exception as exc:
        logger.debug("Failed to emit ToolCalled event: %s", exc)


def emit_tool_completed_event(
    session_id: str,
    tool_name: str,
    call_id: str,
    result: str,
    duration_ms: int = 0,
) -> None:
    """Emit a ToolCompleted event to the event bus.

    Called when a tool execution completes successfully.
    """
    try:
        from butler.core.events import create_tool_completed, get_global_event_bus

        result_preview = str(result)[:200] if result else ""
        success = True

        try:
            parsed = json.loads(result) if isinstance(result, str) else result
            if isinstance(parsed, dict) and parsed.get("error"):
                success = False
        except (json.JSONDecodeError, TypeError):
            pass

        event = create_tool_completed(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            success=success,
            duration_ms=duration_ms,
            result_preview=result_preview,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted ToolCompleted event: %s (call_id=%s, success=%s)",
            tool_name,
            call_id,
            success,
        )
    except Exception as exc:
        logger.debug("Failed to emit ToolCompleted event: %s", exc)


def emit_tool_failed_event(
    session_id: str,
    tool_name: str,
    call_id: str,
    error_message: str,
    error_kind: str = "retry",
    duration_ms: int = 0,
) -> None:
    """Emit a ToolFailed event to the event bus.

    Called when a tool execution fails.
    """
    try:
        from butler.core.events import create_tool_failed, get_global_event_bus

        event = create_tool_failed(
            session_id=session_id,
            tool_name=tool_name,
            call_id=call_id,
            error_message=error_message,
            error_kind=error_kind,
            duration_ms=duration_ms,
        )

        bus = get_global_event_bus()
        bus.publish(event)

        logger.debug(
            "Emitted ToolFailed event: %s (call_id=%s, error=%s)",
            tool_name,
            call_id,
            error_message[:100],
        )
    except Exception as exc:
        logger.debug("Failed to emit ToolFailed event: %s", exc)


__all__ = [
    "emit_tool_called_event",
    "emit_tool_completed_event",
    "emit_tool_failed_event",
]
