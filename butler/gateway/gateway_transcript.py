"""Gateway-side transcript rows (slash shortcuts, MCP grounding without loop)."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def record_gateway_tool_action(
    session_key: str,
    *,
    tool_name: str,
    args_preview: str = "",
) -> None:
    """Append a ``tool_action`` row with ``source=gateway``."""
    sk = str(session_key or "").strip()
    name = str(tool_name or "").strip()
    if not sk or not name:
        return
    try:
        from butler.core.session_transcript import record_tool_action

        record_tool_action(
            sk,
            tool_name=name[:64],
            args_preview=str(args_preview or "")[:400],
            source="gateway",
        )
    except Exception as exc:
        logger.debug("gateway tool_action skipped: %s", exc)


__all__ = ["record_gateway_tool_action"]
