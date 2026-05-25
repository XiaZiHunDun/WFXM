"""MCP connection manager (per-session or process-global)."""

from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from typing import Any

from butler.mcp.async_runner import run_mcp_async
from butler.mcp.config import (
    load_mcp_servers,
    max_tools,
    session_scoped,
    tool_allowed_by_policy,
)
from butler.mcp.types import McpServerConfig, McpServerStatus, McpToolRef

logger = logging.getLogger(__name__)


class _ServerHandle:
    __slots__ = (
        "config",
        "session",
        "cleanup",
        "status",
    )

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self.session: Any = None
        self.cleanup: Any = None
        self.status = McpServerStatus(
            server_id=config.server_id,
            transport=config.transport,
        )


class McpConnectionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._global_handles: dict[str, _ServerHandle] = {}
        self._session_handles: dict[str, dict[str, _ServerHandle]] = {}
        self._tool_refs: dict[str, dict[str, McpToolRef]] = {}
        self._last_errors: dict[str, str] = {}

    def _scope_key(self, session_key: str) -> str:
        if session_scoped():
            return str(session_key or "").strip() or "default"
        return "__global__"

    def _handles_for(self, session_key: str) -> dict[str, _ServerHandle]:
        sk = self._scope_key(session_key)
        if sk == "__global__":
            return self._global_handles
        with self._lock:
            if sk not in self._session_handles:
                self._session_handles[sk] = {}
            return self._session_handles[sk]

    def disconnect_session(self, session_key: str) -> None:
        sk = self._scope_key(session_key)
        with self._lock:
            handles = self._session_handles.pop(sk, None)
            self._tool_refs.pop(sk, None)
        if not handles:
            return
        for handle in handles.values():
            self._close_handle(handle)

    def disconnect_all(self) -> None:
        with self._lock:
            sessions = list(self._session_handles.keys())
            for sk in sessions:
                self.disconnect_session(sk)
            for handle in list(self._global_handles.values()):
                self._close_handle(handle)
            self._global_handles.clear()

    def _close_handle(self, handle: _ServerHandle) -> None:
        if handle.cleanup is None:
            return
        try:
            run_mcp_async(handle.cleanup(), timeout=30.0)
        except Exception as exc:
            logger.debug("MCP cleanup %s: %s", handle.config.server_id, exc)
        handle.session = None
        handle.cleanup = None
        handle.status.connected = False

    def ensure_connected(
        self,
        session_key: str,
        *,
        workspace: Path | None = None,
    ) -> list[McpToolRef]:
        from butler.mcp.bridge import build_tool_refs

        sk = self._scope_key(session_key)
        configs = load_mcp_servers(workspace=workspace)
        handles = self._handles_for(session_key)
        refs: list[McpToolRef] = []

        for cfg in configs:
            handle = handles.get(cfg.server_id)
            if handle is None:
                handle = _ServerHandle(cfg)
                handles[cfg.server_id] = handle
            if handle.status.degraded and handle.status.last_error:
                continue
            if not handle.status.connected:
                try:
                    self._connect_handle(handle, workspace=workspace)
                except Exception as exc:
                    msg = str(exc)[:300]
                    handle.status.last_error = msg
                    handle.status.degraded = True
                    self._last_errors[f"{sk}:{cfg.server_id}"] = msg
                    logger.warning("MCP connect %s failed: %s", cfg.server_id, exc)
                    continue
            session_tools = getattr(handle, "_cached_tools", None)
            if session_tools is None:
                continue
            refs.extend(
                build_tool_refs(cfg, session_tools)[: max(0, max_tools() - len(refs))]
            )
            if len(refs) >= max_tools():
                break

        with self._lock:
            self._tool_refs[sk] = {r.registered_name: r for r in refs}
        return refs[: max_tools()]

    def _connect_handle(self, handle: _ServerHandle, *, workspace: Path | None) -> None:
        cfg = handle.config

        async def _run() -> tuple[Any, list[Any], Any]:
            if cfg.transport == "stdio":
                from butler.mcp.client_stdio import connect_stdio

                return await connect_stdio(cfg, workspace=workspace)
            from butler.mcp.client_http import connect_http

            return await connect_http(cfg, workspace=workspace)

        session, tools, cleanup = run_mcp_async(
            _run(),
            timeout=cfg.timeout_seconds + 15.0,
        )
        filtered = [
            t
            for t in tools
            if tool_allowed_by_policy(cfg.tools, getattr(t, "name", ""))
        ]
        handle.session = session
        handle.cleanup = cleanup
        handle._cached_tools = filtered  # type: ignore[attr-defined]
        handle.status.connected = True
        handle.status.tool_count = len(filtered)
        handle.status.last_error = ""
        handle.status.degraded = False

    def get_tool_ref(self, session_key: str, registered_name: str) -> McpToolRef | None:
        sk = self._scope_key(session_key)
        with self._lock:
            bucket = self._tool_refs.get(sk) or {}
            return bucket.get(registered_name)

    def call_tool(
        self,
        session_key: str,
        ref: McpToolRef,
        arguments: dict[str, Any],
        *,
        workspace: Path | None = None,
    ) -> str:
        handles = self._handles_for(session_key)
        handle = handles.get(ref.server_id)
        if handle is None or not handle.session:
            self.ensure_connected(session_key, workspace=workspace)
            handle = handles.get(ref.server_id)
        if handle is None or not handle.session:
            return _error_payload(ref.registered_name, "MCP server not connected")

        cfg = handle.config
        timeout = cfg.timeout_seconds

        async def _call() -> str:
            if cfg.transport == "stdio":
                from butler.mcp.client_stdio import call_stdio_tool

                return await asyncio.wait_for(
                    call_stdio_tool(handle.session, ref.original_name, arguments),
                    timeout=timeout,
                )
            from butler.mcp.client_http import call_http_tool

            return await asyncio.wait_for(
                call_http_tool(handle.session, ref.original_name, arguments),
                timeout=timeout,
            )

        try:
            return run_mcp_async(_call(), timeout=timeout + 10.0)
        except Exception as exc:
            handle.status.degraded = True
            handle.status.last_error = str(exc)[:300]
            return _error_payload(ref.registered_name, str(exc))


    def status_snapshot(self, session_key: str = "") -> list[McpServerStatus]:
        sk = self._scope_key(session_key)
        with self._lock:
            if sk == "__global__":
                handles = dict(self._global_handles)
            else:
                handles = dict(self._session_handles.get(sk) or {})
        return [h.status for h in handles.values()]


def _error_payload(tool: str, message: str) -> str:
    import json

    return json.dumps({
        "ok": False,
        "error": message,
        "tool": tool,
        "code": "MCP_ERROR",
    }, ensure_ascii=False)


_MANAGER = McpConnectionManager()


def get_manager() -> McpConnectionManager:
    return _MANAGER
