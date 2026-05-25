"""HTTP / SSE MCP client transport."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.mcp.config import validate_http_url
from butler.mcp.types import McpServerConfig

logger = logging.getLogger(__name__)


async def connect_http(
    config: McpServerConfig,
    *,
    workspace: Path | None = None,
) -> tuple[Any, list[Any], Any]:
    del workspace  # reserved for future workspace-scoped headers
    err = validate_http_url(config)
    if err:
        raise ValueError(err)

    from mcp import ClientSession

    headers = dict(config.headers or {})
    url = config.url
    transport = None
    read_stream = None
    write_stream = None

    if config.sse:
        from mcp.client.sse import sse_client

        transport = sse_client(url, headers=headers)
        read_stream, write_stream = await transport.__aenter__()
    else:
        from mcp.client.streamable_http import streamablehttp_client

        transport = streamablehttp_client(url, headers=headers)
        opened = await transport.__aenter__()
        if isinstance(opened, tuple) and len(opened) >= 2:
            read_stream, write_stream = opened[0], opened[1]
        else:
            read_stream, write_stream = opened, None

    if write_stream is None:
        raise RuntimeError("HTTP MCP transport did not provide write stream")

    session = ClientSession(read_stream, write_stream)
    await session.__aenter__()
    await session.initialize()
    listed = await session.list_tools()
    tools = list(getattr(listed, "tools", None) or [])

    async def cleanup() -> None:
        try:
            await session.__aexit__(None, None, None)
        except Exception as exc:
            logger.debug("MCP http session close: %s", exc)
        if transport is not None:
            try:
                await transport.__aexit__(None, None, None)
            except Exception as exc:
                logger.debug("MCP http transport close: %s", exc)

    return session, tools, cleanup


async def call_http_tool(session: Any, tool_name: str, arguments: dict[str, Any]) -> str:
    from butler.mcp.client_stdio import json_dumps_result

    result = await session.call_tool(tool_name, arguments)
    parts: list[str] = []
    for content in getattr(result, "content", None) or []:
        text = getattr(content, "text", None)
        parts.append(str(text) if text is not None else str(content))
    return "\n".join(parts) if parts else json_dumps_result(result)
