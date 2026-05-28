"""Stdio MCP client transport."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.mcp.config import validate_stdio_command
from butler.mcp.types import McpServerConfig

logger = logging.getLogger(__name__)


def _build_stdio_env(config: McpServerConfig) -> dict[str, str]:
    from butler.tools.path_safety import safe_subprocess_env

    base = safe_subprocess_env()
    for key, value in (config.env or {}).items():
        if value is not None:
            base[str(key)] = str(value)
    return base


def _resolve_cwd(config: McpServerConfig, workspace: Path | None) -> str | None:
    if config.cwd:
        return str(Path(config.cwd).expanduser())
    if workspace is not None and workspace.is_dir():
        return str(workspace)
    return None


async def connect_stdio(
    config: McpServerConfig,
    *,
    workspace: Path | None = None,
) -> tuple[Any, list[Any], Any]:
    """Return (session, tools, cleanup_async_callable)."""
    err = validate_stdio_command(config)
    if err:
        raise ValueError(err)

    from mcp import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client

    params = StdioServerParameters(
        command=config.command,
        args=list(config.args),
        env=_build_stdio_env(config),
        cwd=_resolve_cwd(config, workspace),
    )
    transport = stdio_client(params)
    read_stream, write_stream = await transport.__aenter__()
    session = ClientSession(read_stream, write_stream)
    await session.__aenter__()
    await session.initialize()
    listed = await session.list_tools()
    tools = list(getattr(listed, "tools", None) or [])

    async def cleanup() -> None:
        try:
            await session.__aexit__(None, None, None)
        except Exception as exc:
            logger.debug("MCP stdio session close: %s", exc)
        try:
            await transport.__aexit__(None, None, None)
        except Exception as exc:
            logger.debug("MCP stdio transport close: %s", exc)

    return session, tools, cleanup


async def call_stdio_tool(session: Any, tool_name: str, arguments: dict[str, Any]) -> str:
    result = await session.call_tool(tool_name, arguments)
    parts: list[str] = []
    for content in getattr(result, "content", None) or []:
        text = getattr(content, "text", None)
        parts.append(str(text) if text is not None else str(content))
    return "\n".join(parts) if parts else json_dumps_result(result)


def json_dumps_result(result: Any) -> str:
    import json

    try:
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
    except Exception as exc:
        logger.debug("json dumps result skipped: %s", exc)
    return str(result)
