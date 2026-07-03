"""Install scan best-effort helpers (P0-A)."""

from __future__ import annotations

import logging

from butler.mcp.types import McpServerConfig

logger = logging.getLogger(__name__)


def validate_stdio_command_scan_safe(server_id: str, command: str) -> list[str]:
    """Return issue codes when stdio command validation fails."""
    try:
        from butler.mcp.config import validate_stdio_command

        cfg = McpServerConfig(server_id=server_id, transport="stdio", command=command)
        err = validate_stdio_command(cfg)
        if err:
            return ["command_denied"]
    except Exception as exc:
        logger.debug("pre install scan mcp skipped: %s", exc)
    return []
