"""Gateway-side transcript rows (slash shortcuts, MCP grounding without loop)."""

from __future__ import annotations

from butler.gateway.gateway_transcript_ops import record_gateway_tool_action_safe


def record_gateway_tool_action(
    session_key: str,
    *,
    tool_name: str,
    args_preview: str = "",
) -> None:
    """Append a ``tool_action`` row with ``source=gateway``."""
    record_gateway_tool_action_safe(
        session_key,
        tool_name=tool_name,
        args_preview=args_preview,
    )


__all__ = ["record_gateway_tool_action"]
