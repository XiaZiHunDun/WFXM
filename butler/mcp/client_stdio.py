"""Stdio MCP client transport."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.mcp.config import validate_stdio_command
from butler.mcp.types import McpServerConfig

logger = logging.getLogger(__name__)


_PROTECTED_ENV_KEYS = frozenset({
    "PATH", "HOME", "USER", "SHELL", "LOGNAME", "LANG",
    "LD_PRELOAD", "LD_LIBRARY_PATH", "PYTHONPATH",
})


def _merge_stdio_path(host_path: str) -> str:
    """Ensure stdio MCP subprocesses can find ``sh`` and allowlisted commands.

    Gateway systemd may load ``.env`` with ``PATH=...:$PATH`` where ``$PATH`` is
    literal and ``/bin`` is missing — ``npx`` then fails with ``spawn sh ENOENT``.
    """
    required = (
        "/usr/local/sbin",
        "/usr/local/bin",
        "/usr/sbin",
        "/usr/bin",
        "/sbin",
        "/bin",
    )
    parts: list[str] = []
    seen: set[str] = set()
    for segment in str(host_path or "").split(":"):
        s = segment.strip()
        if not s or s == "$PATH":
            continue
        if s not in seen:
            parts.append(s)
            seen.add(s)
    for req in required:
        if req not in seen:
            parts.append(req)
            seen.add(req)
    nvm = [p for p in parts if "/.nvm/versions/node/" in p]
    if nvm:
        other = [p for p in parts if p not in nvm]
        return ":".join(nvm + other)
    return ":".join(parts)


def _build_stdio_env(config: McpServerConfig) -> dict[str, str]:
    import os

    from butler.tools.path_safety import safe_subprocess_env

    base = safe_subprocess_env()
    host_path = os.environ.get("PATH", "").strip()
    base["PATH"] = _merge_stdio_path(host_path) if host_path else base["PATH"]
    for key, value in (config.env or {}).items():
        if value is not None:
            k = str(key)
            if k.upper() in _PROTECTED_ENV_KEYS:
                logger.warning("MCP env override blocked for protected key: %s", k)
                continue
            base[k] = str(value)
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
        from butler.mcp.client_stdio_ops import (
            close_stdio_session_safe,
            close_stdio_transport_safe,
        )

        await close_stdio_session_safe(session)
        await close_stdio_transport_safe(transport)

    return session, tools, cleanup


async def call_stdio_tool(session: Any, tool_name: str, arguments: dict[str, Any]) -> str:
    result = await session.call_tool(tool_name, arguments)
    parts: list[str] = []
    for content in getattr(result, "content", None) or []:
        text = getattr(content, "text", None)
        parts.append(str(text) if text is not None else str(content))
    return "\n".join(parts) if parts else json_dumps_result(result)


def json_dumps_result(result: Any) -> str:
    from butler.mcp.client_stdio_ops import json_dumps_mcp_result_safe

    return json_dumps_mcp_result_safe(result)
