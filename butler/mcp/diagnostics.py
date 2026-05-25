"""MCP section for /诊断."""

from __future__ import annotations

from butler.mcp.registry_hook import mcp_status_lines


def format_mcp_diagnostic_lines(session_key: str) -> list[str]:
    return mcp_status_lines(session_key)
