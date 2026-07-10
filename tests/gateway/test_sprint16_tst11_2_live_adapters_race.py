"""Sprint 16 TST-11-2 → R1-12 — live-adapter registry race test.

Original audit (Sprint 16):
  ``butler.gateway.platforms.wechat_ilink._LIVE_ADAPTERS`` was a
  module-level ``dict[str, Any] = {}`` with no lock. The
  ``connect()`` and ``disconnect()`` paths each touched it from
  the long-poll loop and from the one-shot ``send_wechat_direct``
  helper, with 0 race-test coverage.

R1-12 (this iteration):
  The bare dict was replaced with :class:`AdapterRegistry` (a
  ``WeakValueDictionary`` + ``threading.RLock``). The
  sprint-16 race tests are kept and adapted to the new API so we
  keep regression coverage on the *behaviour* (concurrent
  register / unregister / lookup semantics) while the *shape*
  shifts from ``dict`` to ``AdapterRegistry``.

Test surface:
  - Sequential: register / unregister / contains / len
  - Concurrent distinct tokens: N threads, N entries
  - Concurrent same token: last-writer-wins
  - Concurrent register / unregister / lookup: no KeyError, no
    inconsistent reads
  - Static contract: registry is the new module-level name; the
    old ``_LIVE_ADAPTERS`` dict is gone (R1-12 audit target).
"""

from __future__ import annotations

import asyncio
import importlib
import inspect
import threading
from typing import Any
from unittest.mock import MagicMock

import pytest

from butler.gateway.platforms import wechat_ilink
from butler.gateway.platforms.wechat_ilink_registry import (
    AdapterRegistry,
    _ADAPTER_REGISTRY,
)


# ── 通用 fixture: 清空 singleton, 测试间互不污染 ──


@pytest.fixture(autouse=True)
def _isolate_live_adapters():
    """每个测试前后清空 singleton, 避免污染。"""
    # Snapshot so we can restore after; per-test isolation is critical
    # because the singleton is module-level and shared across tests.
    snapshot = list(_ADAPTER_REGISTRY._adapters.items())  # type: ignore[attr-defined]
    with _ADAPTER_REGISTRY._lock:  # type: ignore[attr-defined]
        _ADAPTER_REGISTRY._adapters.clear()  # type: ignore[attr-defined]
    try:
        yield
    finally:
        with _ADAPTER_REGISTRY._lock:  # type: ignore[attr-defined]
            _ADAPTER_REGISTRY._adapters.clear()  # type: ignore[attr-defined]
            for k, v in snapshot:
                _ADAPTER_REGISTRY._adapters[k] = v  # type: ignore[attr-defined]


def _make_fake_adapter(token: str) -> MagicMock:
    """构造一个 fake adapter, 模拟 connect/disconnect 的注册副作用。

    只设 ``_token`` 属性, 因为 registry 只看 token。
    """
    adapter = MagicMock()  # noqa: magicmock-no-spec — live adapters race shim (adapter)
    adapter._token = token
    return adapter


def _register(adapter: MagicMock) -> None:
    """模拟 ``_start_poll_and_register`` 的最后一行: ``_ADAPTER_REGISTRY.register(adapter._token, adapter)``。"""
    _ADAPTER_REGISTRY.register(adapter._token, adapter)


def _unregister(adapter: MagicMock) -> None:
    """模拟 ``disconnect()`` 的第一行: ``_ADAPTER_REGISTRY.unregister(adapter._token)``。"""
    _ADAPTER_REGISTRY.unregister(adapter._token)


# ── 顺序: 基本契约 ──


class TestSequentialSemantics:
    def test_register_then_lookup(self):
        """register 后, _ADAPTER_REGISTRY.get(token) 应返回该 adapter。"""
        a = _make_fake_adapter("token-a")
        _register(a)
        assert _ADAPTER_REGISTRY.get("token-a") is a

    def test_register_disconnect_unregister(self):
        """register → unregister 后, registry 不应再含该 token。"""
        a = _make_fake_adapter("token-b")
        _register(a)
        assert "token-b" in _ADAPTER_REGISTRY
        _unregister(a)
        assert "token-b" not in _ADAPTER_REGISTRY

    def test_unregister_missing_token_is_noop(self):
        """unregister 未注册的 token → 返回 False, registry 不变。"""
        a = _make_fake_adapter("never-registered")
        _unregister(a)  # 模拟重复 disconnect
        assert "never-registered" not in _ADAPTER_REGISTRY
        assert len(_ADAPTER_REGISTRY) == 0

    def test_register_overwrites_previous(self):
        """同 token 重新 register → 新 adapter 覆盖旧 adapter (last-writer-wins)。"""
        a1 = _make_fake_adapter("token-c")
        a2 = _make_fake_adapter("token-c")
        _register(a1)
        _register(a2)
        assert _ADAPTER_REGISTRY.get("token-c") is a2
        assert _ADAPTER_REGISTRY.get("token-c") is not a1

    def test_disconnect_then_reconnect(self):
        """unregister → register: 旧 adapter 失效, 新 adapter 上位。"""
        a1 = _make_fake_adapter("token-d")
        a2 = _make_fake_adapter("token-d")
        _register(a1)
        _unregister(a1)
        _register(a2)
        assert _ADAPTER_REGISTRY.get("token-d") is a2


# ── 并发: 不同 token 互不干扰 ──


class TestConcurrentDistinctTokens:
    def test_concurrent_register_distinct_tokens_all_succeed(self):
        """N 个线程各 register 不同 token → 全部进入 registry。"""
        N = 32
        barrier = threading.Barrier(N)
        adapters = [_make_fake_adapter(f"distinct-{i}") for i in range(N)]

        def do_register(adapter: MagicMock) -> None:
            barrier.wait()
            _register(adapter)

        threads = [
            threading.Thread(target=do_register, args=(a,))
            for a in adapters
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "register thread hung"

        assert _ADAPTER_REGISTRY.live_count() == N, (
            f"expected {N} entries, got {_ADAPTER_REGISTRY.live_count()}"
        )
        for a in adapters:
            assert _ADAPTER_REGISTRY.get(a._token) is a, (
                f"token {a._token} registered adapter mismatch"
            )

    def test_async_gather_register_distinct_tokens_all_succeed(self):
        """asyncio.gather 并发 register 不同 token → 全部进入 registry。"""
        async def reg_all() -> None:
            adapters = [_make_fake_adapter(f"async-{i}") for i in range(20)]
            await asyncio.gather(*(_register_async(a) for a in adapters))
            assert _ADAPTER_REGISTRY.live_count() == 20
            for a in adapters:
                assert _ADAPTER_REGISTRY.get(a._token) is a

        asyncio.run(reg_all())


async def _register_async(adapter: MagicMock) -> None:
    """async 版本的 register, 模拟 await 间隔。"""
    await asyncio.sleep(0)
    _register(adapter)


# ── 并发: 同 token last-writer-wins ──


class TestConcurrentSameToken:
    def test_concurrent_register_same_token_one_wins(self):
        """N 个线程同 token 并发 register → registry 终态应只有一个, 是某个 thread 的 adapter。"""
        N = 16
        token = "shared-token"
        barrier = threading.Barrier(N)
        adapters = [_make_fake_adapter(token) for _ in range(N)]

        def do_register(adapter: MagicMock) -> None:
            barrier.wait()
            _register(adapter)

        threads = [
            threading.Thread(target=do_register, args=(a,))
            for a in adapters
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "register thread hung"

        assert _ADAPTER_REGISTRY.live_count() == 1, (
            f"expected 1 entry for shared token, got {_ADAPTER_REGISTRY.live_count()}"
        )
        winner = _ADAPTER_REGISTRY.get(token)
        assert winner in adapters, "winner must be one of the registered adapters"


# ── 并发: connect/disconnect 交错 ──


class TestConcurrentConnectDisconnect:
    def test_register_unregister_register_no_lost_updates(self):
        """交替 register/unregister: 最终状态应一致。"""
        token = "flap-token"
        N = 50
        a = _make_fake_adapter(token)
        barrier = threading.Barrier(N)

        def do_flap(idx: int) -> None:
            barrier.wait()
            if idx % 2 == 0:
                _register(a)
            else:
                _unregister(a)

        threads = [
            threading.Thread(target=do_flap, args=(i,)) for i in range(N)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)

        # 收尾: unregister 一次, 验证 registry 一致
        _unregister(a)
        assert "flap-token" not in _ADAPTER_REGISTRY

    def test_concurrent_unregister_and_lookup(self):
        """一个线程 unregister, 多个线程同时 lookup → lookup 不应抛任何异常。"""
        token = "lookup-race"
        a = _make_fake_adapter(token)
        _register(a)

        N_LOOKUP = 16
        barrier = threading.Barrier(N_LOOKUP + 1)
        results: list[Any] = []
        results_lock = threading.Lock()

        def do_lookup() -> None:
            barrier.wait()
            v = _ADAPTER_REGISTRY.get(token)
            with results_lock:
                results.append(v)

        def do_unregister() -> None:
            barrier.wait()
            _unregister(a)

        lookup_threads = [
            threading.Thread(target=do_lookup) for _ in range(N_LOOKUP)
        ]
        unreg_thread = threading.Thread(target=do_unregister)

        for t in lookup_threads:
            t.start()
        unreg_thread.start()
        for t in lookup_threads:
            t.join(timeout=5)
        unreg_thread.join(timeout=5)

        # 所有 lookup 应返回 a 或 None, 不抛任何异常
        for r in results:
            assert r is a or r is None, (
                f"lookup 期间不应出现意料外的值: {r!r}"
            )


# ── 静态契约: 适配 R1-12 的新 shape ──


class TestStaticContract:
    def test_registry_is_module_level_adapter_registry(self):
        """R1-12: wechat_ilink 必须暴露模块级 ``_ADAPTER_REGISTRY`` (AdapterRegistry)。"""
        assert hasattr(wechat_ilink, "_ADAPTER_REGISTRY"), (
            "wechat_ilink must expose module-level _ADAPTER_REGISTRY (R1-12)"
        )
        assert isinstance(wechat_ilink._ADAPTER_REGISTRY, AdapterRegistry), (
            f"_ADAPTER_REGISTRY 应为 AdapterRegistry, 实际 "
            f"{type(wechat_ilink._ADAPTER_REGISTRY)}"
        )

    def test_old_live_adapters_dict_is_gone(self):
        """R1-12: 模块级 ``_LIVE_ADAPTERS: dict`` 已被 ``_ADAPTER_REGISTRY`` 替代。

        如果 ``_LIVE_ADAPTERS`` 仍以 dict 形式存在, 说明 R1-12 的替换没生效。
        """
        if hasattr(wechat_ilink, "_LIVE_ADAPTERS"):
            assert not isinstance(wechat_ilink._LIVE_ADAPTERS, dict), (
                "_LIVE_ADAPTERS dict shape was the R1-12 audit target; "
                "the new _ADAPTER_REGISTRY (AdapterRegistry) replaces it."
            )

    def test_disconnect_uses_registry_unregister(self):
        """disconnect() 经 adapter_lifecycle 调用 ``_ADAPTER_REGISTRY.unregister``（ENG-13）。"""
        from butler.gateway.platforms.wechat_ilink import WeChatAdapter
        from butler.gateway.platforms.wechat_ilink import adapter_lifecycle

        adapter_source = inspect.getsource(WeChatAdapter.disconnect)
        lifecycle_source = inspect.getsource(adapter_lifecycle.disconnect)
        assert "adapter_lifecycle" in adapter_source, (
            "WeChatAdapter.disconnect 应委托 adapter_lifecycle"
        )
        assert "_ADAPTER_REGISTRY.unregister" in lifecycle_source, (
            "adapter_lifecycle.disconnect 应使用 _ADAPTER_REGISTRY.unregister"
        )
        assert "_LIVE_ADAPTERS" not in lifecycle_source, (
            "disconnect 不应再 touch _LIVE_ADAPTERS (R1-12 已替换为 registry)"
        )

    def test_start_poll_assigns_via_registry(self):
        """``_start_poll_and_register`` 末尾应执行 ``_ADAPTER_REGISTRY.register(...)``。"""
        from butler.gateway.platforms import wechat_ilink_phases

        source = inspect.getsource(wechat_ilink_phases._start_poll_and_register)
        assert "_ADAPTER_REGISTRY.register(" in source, (
            "_start_poll_and_register 应在末尾通过 _ADAPTER_REGISTRY.register 注册"
        )
        assert "_LIVE_ADAPTERS" not in source, (
            "_start_poll_and_register 不应再 touch _LIVE_ADAPTERS"
        )

    def test_lookup_uses_get_with_default(self):
        """调用方 (line 1257 附近) 必须用 ``.get(resolved_token)`` 而非裸下标 ``[token]``。"""
        import inspect

        from butler.gateway.platforms import wechat_ilink

        source = inspect.getsource(wechat_ilink)
        for line in source.splitlines():
            stripped = line.strip()
            # 允许 .get(...) 和 .pop(..., None) 调用; 禁止裸 _ADAPTER_REGISTRY[xxx] 读取
            if "_ADAPTER_REGISTRY[" in stripped:
                pytest.fail(
                    f"found unsafe read _ADAPTER_REGISTRY[...]: {stripped!r}"
                )
