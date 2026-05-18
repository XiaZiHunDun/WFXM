"""Minimal MCP-compatible JSON-RPC server over stdio for Butler tools."""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from typing import Any

logger = logging.getLogger(__name__)


class MCPServer:
    """Minimal MCP Server exposing Butler tools via JSON-RPC 2.0 over stdio.

    Implements the MCP protocol subset needed for tool discovery and execution:
    - initialize / initialized handshake
    - tools/list - enumerate available tools
    - tools/call - execute a tool
    """

    PROTOCOL_VERSION = "2024-11-05"
    SERVER_NAME = "butler-mcp"
    SERVER_VERSION = "0.1.0"

    def __init__(self) -> None:
        self._initialized = False
        self._tools_loaded = False

    def _ensure_tools(self) -> None:
        """Lazy-load Butler tools."""
        if self._tools_loaded:
            return
        import butler.tools.file_tools  # noqa: F401
        import butler.tools.code_tools  # noqa: F401
        import butler.tools.shell_tools  # noqa: F401
        import butler.tools.git_tools  # noqa: F401
        import butler.tools.patch_tool  # noqa: F401
        import butler.tools.code_graph  # noqa: F401
        import butler.tools.worktree_tools  # noqa: F401
        self._tools_loaded = True

    async def handle_message(self, message: dict[str, Any]) -> dict[str, Any] | None:
        """Handle a single JSON-RPC 2.0 message."""
        method = message.get("method", "")
        msg_id = message.get("id")
        params = message.get("params", {}) or {}

        if method == "initialize":
            return self._handle_initialize(msg_id, params)
        if method == "notifications/initialized":
            self._initialized = True
            return None
        if method == "tools/list":
            return self._handle_tools_list(msg_id, params)
        if method == "tools/call":
            return await self._handle_tools_call(msg_id, params)
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "error": {"code": -32601, "message": f"Method not found: {method}"},
        }

    def _handle_initialize(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": self.PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.SERVER_NAME, "version": self.SERVER_VERSION},
            },
        }

    def _handle_tools_list(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tools()
        from butler.tools.registry import tool_registry

        tools = []
        for tool_def in tool_registry.get_definitions():
            func = tool_def.get("function", {})
            tools.append(
                {
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "inputSchema": func.get("parameters", {}),
                }
            )

        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}

    async def _handle_tools_call(self, msg_id: Any, params: dict[str, Any]) -> dict[str, Any]:
        self._ensure_tools()
        from butler.tools.registry import tool_registry

        tool_name = params.get("name", "")
        arguments = params.get("arguments", {}) or {}

        try:
            result = await tool_registry.dispatch(tool_name, arguments)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": result}],
                    "isError": False,
                },
            }
        except Exception as e:
            logger.exception("tools/call failed for %s", tool_name)
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(e)})}],
                    "isError": True,
                },
            }

    async def run_stdio(self) -> None:
        """Run the MCP server reading from stdin and writing to stdout."""
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        read_proto = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: read_proto, sys.stdin.buffer)

        transport, proto = await loop.connect_write_pipe(
            asyncio.streams.FlowControlMixin,
            sys.stdout.buffer,
        )
        writer = asyncio.StreamWriter(transport, proto, reader, loop)

        while True:
            try:
                line = await reader.readline()
                if not line:
                    break
                stripped = line.decode("utf-8", errors="replace").strip()
                if not stripped:
                    continue
                message = json.loads(stripped)
                response = await self.handle_message(message)
                if response is not None:
                    writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
                    await writer.drain()
            except json.JSONDecodeError:
                continue
            except Exception as e:
                logger.error("MCP server error: %s", e)
                break


class MCPClientBridge:
    """Bridge to consume external MCP servers and register their tools in Butler."""

    def __init__(self, server_command: list[str], server_name: str = ""):
        self.server_command = server_command
        self.server_name = server_name or (
            server_command[0] if server_command else "mcp"
        )
        self._process: asyncio.subprocess.Process | None = None
        self._msg_id = 0

    async def connect(self) -> bool:
        """Start the MCP server process and initialize."""
        try:
            self._process = await asyncio.create_subprocess_exec(
                *self.server_command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            result = await self._send_request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "butler", "version": "0.1.0"},
                },
            )
            if result and "protocolVersion" in result:
                await self._send_notification("notifications/initialized", {})
                return True
            return False
        except Exception as e:
            logger.error("MCP client connect failed: %s", e)
            return False

    async def list_tools(self) -> list[dict[str, Any]]:
        """Get available tools from the MCP server."""
        result = await self._send_request("tools/list", {})
        return result.get("tools", []) if result else []

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> str:
        """Call a tool on the MCP server."""
        result = await self._send_request(
            "tools/call", {"name": name, "arguments": arguments}
        )
        if result and "content" in result:
            texts = [
                c.get("text", "")
                for c in result["content"]
                if c.get("type") == "text"
            ]
            return "\n".join(texts)
        return json.dumps(result or {"error": "No response"}, ensure_ascii=False)

    async def register_tools_in_butler(self) -> int:
        """Discover MCP server tools and register them in Butler's tool registry."""
        from butler.tools.registry import tool_registry

        tools = await self.list_tools()
        server_tag = self.server_name.replace(" ", "_").replace("/", "_")

        for tool in tools:
            raw_name = tool.get("name", "")
            name = f"mcp_{server_tag}_{raw_name}"

            def make_handler(captured: str):
                async def handler(**kwargs: Any) -> str:
                    return await self.call_tool(captured, kwargs)

                return handler

            tool_registry.register(
                name=name,
                description=f"[MCP:{self.server_name}] {tool.get('description', '')}",
                parameters=tool.get(
                    "inputSchema", {"type": "object", "properties": {}}
                ),
                handler=make_handler(raw_name),
                is_async=True,
                category="mcp",
            )
        return len(tools)

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any] | None:
        if not self._process or not self._process.stdin or not self._process.stdout:
            return None
        self._msg_id += 1
        msg = {"jsonrpc": "2.0", "id": self._msg_id, "method": method, "params": params}
        self._process.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

        try:
            line = await asyncio.wait_for(self._process.stdout.readline(), timeout=60)
            if line:
                resp = json.loads(line.decode("utf-8", errors="replace").strip())
                if "error" in resp:
                    return None
                return resp.get("result")
        except (asyncio.TimeoutError, json.JSONDecodeError):
            pass
        return None

    async def _send_notification(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            return
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self._process.stdin.write((json.dumps(msg, ensure_ascii=False) + "\n").encode("utf-8"))
        await self._process.stdin.drain()

    async def disconnect(self) -> None:
        if self._process:
            self._process.terminate()
            try:
                await asyncio.wait_for(self._process.wait(), timeout=5)
            except asyncio.TimeoutError:
                self._process.kill()
            self._process = None


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    server = MCPServer()
    await server.run_stdio()


if __name__ == "__main__":
    asyncio.run(main())
