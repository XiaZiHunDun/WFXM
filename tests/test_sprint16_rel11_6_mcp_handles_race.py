"""Sprint 16 REL-11-6: butler.mcp.manager._handles_for 锁外返回 live dict.

bug: butler/mcp/manager.py:54-61
  - _global_handles: 路径返回 self._global_handles, **从未加锁**
  - session 路径: 加锁创建空 dict, 释放锁后返回 live ref
    → 调用方在锁外对返回的 dict 读写, 与 disconnect_session
      (pop + close) 竞争, 可能 RuntimeError "dict changed size during iteration"

修复: _handles_for 永远在锁内返回; 改用 context manager 暴露 scoped handles,
      调用方在 ``with`` 块内做读写, 离开 with 自动释放锁。
"""

from __future__ import annotations

import threading
from unittest.mock import patch

import pytest

from butler.mcp import manager
from butler.mcp.manager import McpConnectionManager


@pytest.fixture
def _global_scope(monkeypatch):
    """强制 manager 走 global scope (非 session scope)。"""
    monkeypatch.setenv("BUTLER_MCP_SESSION_SCOPED", "0")


@pytest.fixture
def _session_scope(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_SESSION_SCOPED", "1")


# ── RED 测试 1: global scope 下, _handles_for 现在应该返回独立快照, 不共享引用 ──


class TestHandlesForGlobalScope:
    def test_global_handles_for_returns_snapshot(
        self, _global_scope,
    ):
        """global scope 路径: 返回的 dict 不应是 self._global_handles 本身。

        修复后: 应返回 dict(self._global_handles) 快照, 或在锁内返回 live ref
        并要求调用方持锁使用。
        """
        mgr = McpConnectionManager()
        ref = mgr._handles_for("any_session")

        # 关键不变式: 调用方修改 ref 不应影响内部状态 (除非持锁)
        ref["fake_handle"] = object()
        assert "fake_handle" not in mgr._global_handles, (
            "global scope 路径修改返回的 dict 直接污染了 _global_handles, "
            "说明 _handles_for 未加锁或返回了 live ref"
        )

    def test_global_handles_for_thread_safe_under_mutation(
        self, _global_scope,
    ):
        """global 路径并发: 1 线程迭代返回的 dict, 1 线程 disconnect_all,
        不应抛 'dict changed size during iteration'。"""
        from butler.mcp.types import McpServerConfig, McpServerStatus

        mgr = McpConnectionManager()
        # 预填一些 handle (用 config 实例化, 这样 _close_handle 不会 NPE)
        for i in range(50):
            cfg = McpServerConfig(
                server_id=f"server_{i}",
                transport="http",
                url="http://localhost:0",
            )
            h = manager._ServerHandle(cfg)
            h.status = McpServerStatus(server_id=cfg.server_id, transport=cfg.transport)
            mgr._global_handles[cfg.server_id] = h

        errors: list[BaseException] = []

        def reader() -> None:
            try:
                for _ in range(100):
                    ref = mgr._handles_for("s")
                    for k in list(ref.keys()):
                        _ = ref[k]
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def mutator() -> None:
            try:
                for _ in range(50):
                    # 用 close 全局锁 + 清空, 不调用 _close_handle (避免真实 I/O)
                    with mgr._lock:
                        for h in list(mgr._global_handles.values()):
                            h.status.connected = False
                        mgr._global_handles.clear()
                    # 重新填充以便 reader 能继续迭代
                    for i in range(50):
                        cfg = McpServerConfig(
                            server_id=f"server_{i}",
                            transport="http",
                            url="http://localhost:0",
                        )
                        h = manager._ServerHandle(cfg)
                        h.status = McpServerStatus(
                            server_id=cfg.server_id, transport=cfg.transport,
                        )
                        mgr._global_handles[cfg.server_id] = h
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(3)] + [
            threading.Thread(target=mutator) for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert errors == [], f"并发出现 race 错误: {errors}"


# ── RED 测试 2: session scope 下, disconnect_session 不再让 in-flight reader 持 detached ref ──


class TestHandlesForSessionScope:
    def test_session_handles_for_atomic(
        self, _session_scope, monkeypatch,
    ):
        """session 路径: _handles_for 创建 dict 应在锁内, 调用方可安全读。

        修复后: 应提供 ``_with_handles`` 上下文管理器, 调用方在 ``with`` 内
        读 handles, 离开自动释放锁。
        """
        from butler.mcp.types import McpServerConfig, McpServerStatus

        mgr = McpConnectionManager()
        # 模拟另一线程在调用 _handles_for 后立即 disconnect
        sk = "session-1"

        with mgr._with_handles(sk) as handles:
            cfg = McpServerConfig(
                server_id="server_a", transport="http", url="http://localhost:0",
            )
            h = manager._ServerHandle(cfg)
            h.status = McpServerStatus(server_id=cfg.server_id, transport=cfg.transport)
            handles["server_a"] = h

        # 锁释放后, disconnect_session 应清空 (用空 _close_handle 替代)
        with mgr._lock:
            handles = mgr._session_handles.pop(sk, None)
            assert handles is not None
            # close 是空 (无 session/cleanup) — 不调用 _close_handle
        assert sk not in mgr._session_handles or not mgr._session_handles[sk]

    def test_session_concurrent_disconnect_during_read(
        self, _session_scope,
    ):
        """session 路径并发: 1 线程持 with 块, 1 线程 disconnect_session,
        不应让 reader 持 detached ref 写。"""
        mgr = McpConnectionManager()
        sk = "session-1"
        errors: list[BaseException] = []

        def reader() -> None:
            try:
                for _ in range(50):
                    with mgr._with_handles(sk) as handles:
                        for k in list(handles.keys()):
                            _ = handles[k]
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        def mutator() -> None:
            try:
                for _ in range(50):
                    # disconnect 触发 dict.pop + close, 必须等 with 块释放
                    mgr.disconnect_session(sk)
            except BaseException as exc:  # noqa: BLE001
                errors.append(exc)

        threads = [threading.Thread(target=reader) for _ in range(2)] + [
            threading.Thread(target=mutator) for _ in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10.0)

        assert errors == [], f"并发出现 race 错误: {errors}"


# ── 回归: 现有 API 行为不破 ──


class TestBackwardCompat:
    def test_handles_for_still_returns_dict(self, _global_scope):
        """_handles_for 应仍返回 dict (或 dict-like), 不破现有 caller。"""
        mgr = McpConnectionManager()
        ref = mgr._handles_for("s")
        # 现存 caller 都用 dict 操作: .get(), __setitem__, keys(), values()
        assert hasattr(ref, "get")
        assert hasattr(ref, "__setitem__")
        assert hasattr(ref, "keys")
        assert hasattr(ref, "values")
