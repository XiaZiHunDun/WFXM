"""MCP connection manager (per-session or process-global)."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast

from butler.mcp.async_runner import run_mcp_async
from butler.mcp.config import (
    load_mcp_servers,
    max_tools,
    session_scoped,
    tool_allowed_by_policy,
)
from butler.mcp.types import McpServerConfig, McpServerStatus, McpToolRef

from butler.mcp.manager_ops import (
    close_mcp_handle_safe,
    filter_mcp_servers_by_profile_safe,
    connect_handle_loud,
    call_tool_loud,
)
from butler.mcp.bridge import build_tool_refs
from butler.mcp.client_stdio import (
    connect_stdio,
    call_stdio_tool,
)
from butler.mcp.client_http import (
    connect_http,
    call_http_tool,
)

logger = logging.getLogger(__name__)


class _ServerHandle:
    __slots__ = (
        "config",
        "session",
        "cleanup",
        "status",
        "_cached_tools",
    )

    def __init__(self, config: McpServerConfig) -> None:
        self.config = config
        self.session: Any = None
        self.cleanup: Any = None
        self.status = McpServerStatus(
            server_id=config.server_id,
            transport=config.transport,
        )
        self._cached_tools: list[Any] | None = None


class McpConnectionManager:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._global_handles: dict[str, _ServerHandle] = {}
        self._session_handles: dict[str, dict[str, _ServerHandle]] = {}
        self._tool_refs: dict[str, dict[str, McpToolRef]] = {}

    def _scope_key(self, session_key: str) -> str:
        if session_scoped():
            return str(session_key or "").strip() or "default"
        return "__global__"

    def _handles_for(self, session_key: str) -> dict[str, _ServerHandle]:
        """Return a SNAPSHOT copy of the handles dict for *session_key*.

        Sprint 16 REL-11-6: 之前返回 live dict ref (global 路径甚至未加锁),
        调用方在锁外读写会与 ``disconnect_session`` / ``disconnect_all``
        竞争, 抛 ``RuntimeError: dict changed size during iteration``。

        新契约: 返回 ``dict(handles)`` 快照, 调用方可安全迭代, 但写入
        会丢失 (要写入请用 ``_with_handles`` 上下文管理器)。
        """
        sk = self._scope_key(session_key)
        with self._lock:
            if sk == "__global__":
                return dict(self._global_handles)
            handles = self._session_handles.get(sk)
            return dict(handles) if handles else {}

    @contextlib.contextmanager
    def _with_handles(
        self, session_key: str,
    ) -> Iterator[dict[str, "_ServerHandle"]]:
        """持有 self._lock, 返回 live handles dict ref, 离开 ``with`` 自动释放。

        Sprint 16 REL-11-6: 给需要 "读-改-写" 模式 (如 ensure_connected)
        的调用方用。yield 的是 live ref, 在 ``with`` 块内可安全 ``__setitem__`` /
        ``pop`` / ``keys()`` 迭代; 块外必须重新获取。
        """
        sk = self._scope_key(session_key)
        with self._lock:
            if sk == "__global__":
                yield self._global_handles
                return
            if sk not in self._session_handles:
                self._session_handles[sk] = {}
            yield self._session_handles[sk]

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

        close_mcp_handle_safe(
            handle,
            run_cleanup=lambda: run_mcp_async(handle.cleanup(), timeout=30.0),
        )

    def ensure_connected(
        self,
        session_key: str,
        *,
        workspace: Path | None = None,
    ) -> list[McpToolRef]:

        sk = self._scope_key(session_key)
        configs = load_mcp_servers(workspace=workspace)

        configs = filter_mcp_servers_by_profile_safe(configs, session_key=sk)
        # Sprint 16 REL-11-6: 用 _with_handles 持锁进行 read-modify-write,
        # 避免 _handles_for 返回的 snapshot 被 disconnect_session 异步清空。
        with self._with_handles(session_key) as handles:
            refs = self._ensure_connected_locked(
                sk, handles, configs, workspace=workspace,
            )
        return refs

    def _ensure_connected_locked(
        self,
        sk: str,
        handles: dict[str, "_ServerHandle"],
        configs: list[Any],
        *,
        workspace: Path | None,
    ) -> list[McpToolRef]:

        refs: list[McpToolRef] = []
        for cfg in configs:
            handle = handles.get(cfg.server_id)
            if handle is None:
                handle = _ServerHandle(cfg)
                handles[cfg.server_id] = handle
            if handle.status.degraded and handle.status.last_error:
                continue
            if not handle.status.connected:

                if not connect_handle_loud(
                    handle,
                    server_id=cfg.server_id,
                    run_connect=lambda h=handle: self._connect_handle(h, workspace=workspace),
                ):
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

                return cast(
                    tuple[Any, list[Any], Any],
                    await connect_stdio(cfg, workspace=workspace),
                )

            return cast(
                tuple[Any, list[Any], Any],
                await connect_http(cfg, workspace=workspace),
            )

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
        handle._cached_tools = filtered
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
        # Sprint 16 REL-11-6: snapshot 拿不到可写的 handle ref; 用 _with_handles
        # 持锁拿 live ref, 验证 handle 后立即释放, 后续 await 不持锁。
        with self._with_handles(session_key) as handles:
            handle = handles.get(ref.server_id)
        if handle is None or not handle.session:
            self.ensure_connected(session_key, workspace=workspace)
            with self._with_handles(session_key) as handles:
                handle = handles.get(ref.server_id)
        if handle is None or not handle.session:
            return _error_payload(ref.registered_name, "MCP server not connected")

        cfg = handle.config
        timeout = cfg.timeout_seconds

        async def _call() -> str:
            if cfg.transport == "stdio":

                return await asyncio.wait_for(
                    call_stdio_tool(handle.session, ref.original_name, arguments),
                    timeout=timeout,
                )

            return await asyncio.wait_for(
                call_http_tool(handle.session, ref.original_name, arguments),
                timeout=timeout,
            )


        return cast(
            str,
            call_tool_loud(
                handle,
                server_id=cfg.server_id,
                tool_name=ref.original_name,
                run_call=lambda: run_mcp_async(_call(), timeout=timeout + 10.0),
                on_error=lambda msg: _error_payload(ref.registered_name, msg),
            ),
        )


    def status_snapshot(self, session_key: str = "") -> list[McpServerStatus]:
        sk = self._scope_key(session_key)
        with self._lock:
            if sk == "__global__":
                handles = dict(self._global_handles)
            else:
                handles = dict(self._session_handles.get(sk) or {})
        return [h.status for h in handles.values()]

    def degraded_servers(
        self, session_key: str = "",
    ) -> list[tuple[str, str, str]]:
        """Return ``(server_id, transport, last_error)`` tuples for every
        MCP server currently flagged degraded in *session_key*'s scope.

        Audit R2-6: previously the only signal that a server was down was
        the user-side "Unknown MCP tool" message; operators had no way to
        see which servers are degraded without scraping internal state.
        """
        sk = self._scope_key(session_key)
        with self._lock:
            if sk == "__global__":
                handles = dict(self._global_handles)
            else:
                handles = dict(self._session_handles.get(sk) or {})
        return [
            (h.config.server_id, h.config.transport, h.status.last_error)
            for h in handles.values()
            if h.status.degraded
        ]


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
