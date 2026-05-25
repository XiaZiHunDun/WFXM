"""Optional MCP client bridge (install with ``butler-system[mcp]``)."""

from butler.mcp.config import mcp_enabled, mcp_sdk_available
from butler.mcp.registry_hook import (
    disconnect_mcp_session,
    dispatch_mcp_tool,
    ensure_mcp_for_session,
    get_mcp_tool_definitions,
    is_mcp_tool,
)

__all__ = [
    "mcp_enabled",
    "mcp_sdk_available",
    "disconnect_mcp_session",
    "dispatch_mcp_tool",
    "ensure_mcp_for_session",
    "get_mcp_tool_definitions",
    "is_mcp_tool",
]
