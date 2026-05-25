"""Expose a subset of Butler tools as an MCP Server (stdio, dev use)."""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)

_EXPOSED = (
    "read_file",
    "list_directory",
    "search_files",
    "session_todos_list",
)


def run_stdio_server() -> int:
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError:
        logger.error("Install MCP SDK: pip install butler-system[mcp]")
        return 1

    mcp = FastMCP("butler")

    @mcp.tool(name="read_file", description="Read a file from the active Butler workspace")
    def mcp_read_file(path: str, offset: int = 1, limit: int = 500) -> str:
        return _dispatch_builtin("read_file", {"path": path, "offset": offset, "limit": limit})

    @mcp.tool(name="list_directory", description="List directory entries")
    def mcp_list_directory(path: str = ".") -> str:
        return _dispatch_builtin("list_directory", {"path": path})

    @mcp.tool(name="search_files", description="Ripgrep search in workspace")
    def mcp_search_files(pattern: str, path: str = ".", glob: str = "") -> str:
        args: dict[str, Any] = {"pattern": pattern, "path": path}
        if glob:
            args["glob"] = glob
        return _dispatch_builtin("search_files", args)

    @mcp.tool(name="session_todos_list", description="List session-scoped todos")
    def mcp_session_todos_list() -> str:
        return _dispatch_builtin("session_todos_list", {})

    mcp.run(transport="stdio")
    return 0


def _dispatch_builtin(name: str, args: dict[str, Any]) -> str:
    if name not in _EXPOSED:
        return json.dumps({"ok": False, "error": f"tool not exposed: {name}"})
    from butler.tools.registry import dispatch_tool

    return dispatch_tool(name, args)
