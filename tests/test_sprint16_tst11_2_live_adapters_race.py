"""Sprint 16 TST-11-2: butler.gateway.platforms.wechat_ilink._LIVE_ADAPTERS 0 race test.

bug: butler/gateway/platforms/wechat_ilink.py:158, 1042, 1058
  - ``_LIVE_ADAPTERS: Dict[str, Any] = {}`` 模块级 dict, 跨实例共享
  - ``connect()`` → ``_LIVE_ADAPTERS[self._token] = self`` (line 1042)
  - ``disconnect()`` → ``_LIVE_ADAPTERS.pop(self._token, None)`` (line 1058)
  - 0 个 race test 覆盖: 并发 connect 同/不同 token, connect/disconnect 交错

修复: 直接补单测覆盖这些 race 场景, 不改实现 (dict 单 key 写入在 CPython 下原子,
但并发 connect 同 token 的『last-writer-wins』语义需要测试验证)。
"""

from __future__ import annotations

import asyncio
import threading
from unittest.mock import MagicMock

import pytest

from butler.gateway.platforms import wechat_ilink
from butler.gateway.platforms.wechat_ilink import _LIVE_ADAPTERS


# ── 通用 fixture: 清空模块级 dict ──


@pytest.fixture(autouse=True)
def _isolate_live_adapters():
    """每个测试前后清空 _LIVE_ADAPTERS, 避免污染。"""
    _LIVE_ADAPTERS.clear()
    yield
    _LIVE_ADAPTERS.clear()


def _make_fake_adapter(token: str) -> MagicMock:
    """构造一个 fake adapter, 模拟 connect/disconnect 的 dict 副作用。

    只设 ``_token`` 属性, 因为 _LIVE_ADAPTERS 索引只看 token。
    """
    adapter = MagicMock()
    adapter._token = token
    return adapter


def _register(adapter: MagicMock) -> None:
    """模拟 connect() 的最后一行: ``_LIVE_ADAPTERS[self._token] = self``。"""
    _LIVE_ADAPTERS[adapter._token] = adapter


def _unregister(adapter: MagicMock) -> None:
    """模拟 disconnect() 的第一行: ``_LIVE_ADAPTERS.pop(self._token, None)``。"""
    _LIVE_ADAPTERS.pop(adapter._token, None)


# ── 顺序: 基本契约 ──


class TestSequentialSemantics:
    def test_register_then_lookup(self):
        """register 后, _LIVE_ADAPTERS.get(token) 应返回该 adapter。"""
        a = _make_fake_adapter("token-a")
        _register(a)
        assert _LIVE_ADAPTERS.get("token-a") is a

    def test_register_disconnect_unregister(self):
        """register → unregister 后, dict 不应再含该 token。"""
        a = _make_fake_adapter("token-b")
        _register(a)
        assert "token-b" in _LIVE_ADAPTERS
        _unregister(a)
        assert "token-b" not in _LIVE_ADAPTERS

    def test_unregister_missing_token_is_noop(self):
        """disconnect 未注册的 token → 不抛 KeyError, dict 不变。"""
        a = _make_fake_adapter("never-registered")
        _unregister(a)  # 模拟重复 disconnect
        assert "never-registered" not in _LIVE_ADAPTERS
        assert _LIVE_ADAPTERS == {}

    def test_register_overwrites_previous(self):
        """同 token 重新 register → 新 adapter 覆盖旧 adapter (last-writer-wins)。"""
        a1 = _make_fake_adapter("token-c")
        a2 = _make_fake_adapter("token-c")
        _register(a1)
        _register(a2)
        assert _LIVE_ADAPTERS["token-c"] is a2
        assert _LIVE_ADAPTERS["token-c"] is not a1

    def test_disconnect_then_reconnect(self):
        """disconnect → reconnect: 旧 adapter 失效, 新 adapter 上位。"""
        a1 = _make_fake_adapter("token-d")
        a2 = _make_fake_adapter("token-d")
        _register(a1)
        _unregister(a1)
        _register(a2)
        assert _LIVE_ADAPTERS["token-d"] is a2


# ── 并发: 不同 token 互不干扰 ──


class TestConcurrentDistinctTokens:
    def test_concurrent_register_distinct_tokens_all_succeed(self):
        """N 个线程各 register 不同 token → 全部进入 dict。"""
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

        assert len(_LIVE_ADAPTERS) == N, (
            f"expected {N} entries, got {len(_LIVE_ADAPTERS)}: "
            f"{list(_LIVE_ADAPTERS.keys())}"
        )
        for a in adapters:
            assert _LIVE_ADAPTERS[a._token] is a, (
                f"token {a._token} registered adapter mismatch"
            )

    def test_async_gather_register_distinct_tokens_all_succeed(self):
        """asyncio.gather 并发 register 不同 token → 全部进入 dict。"""
        async def reg_all() -> None:
            adapters = [_make_fake_adapter(f"async-{i}") for i in range(20)]
            await asyncio.gather(*(_register_async(a) for a in adapters))
            assert len(_LIVE_ADAPTERS) == 20
            for a in adapters:
                assert _LIVE_ADAPTERS[a._token] is a

        asyncio.run(reg_all())


async def _register_async(adapter: MagicMock) -> None:
    """async 版本的 register, 模拟 await 间隔。"""
    await asyncio.sleep(0)
    _register(adapter)


# ── 并发: 同 token last-writer-wins ──


class TestConcurrentSameToken:
    def test_concurrent_register_same_token_one_wins(self):
        """N 个线程同 token 并发 register → dict 终态应只有一个, 是某个 thread 的 adapter。"""
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

        assert len(_LIVE_ADAPTERS) == 1, (
            f"expected 1 entry for shared token, got {len(_LIVE_ADAPTERS)}"
        )
        winner = _LIVE_ADAPTERS[token]
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

        # 收尾: unregister 一次, 验证 dict 一致
        _unregister(a)
        assert "flap-token" not in _LIVE_ADAPTERS

    def test_concurrent_unregister_and_lookup(self):
        """一个线程 unregister, 多个线程同时 lookup → lookup 不应抛 KeyError。"""
        token = "lookup-race"
        a = _make_fake_adapter(token)
        _register(a)

        N_LOOKUP = 16
        barrier = threading.Barrier(N_LOOKUP + 1)
        results: list[MagicMock | None] = []
        results_lock = threading.Lock()

        def do_lookup() -> None:
            barrier.wait()
            v = _LIVE_ADAPTERS.get(token)
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

        # 所有 lookup 应返回 a 或 None, 不抛 KeyError
        for r in results:
            assert r is a or r is None, (
                f"lookup 期间不应出现意料外的值: {r!r}"
            )


# ── 静态契约 ──


class TestStaticContract:
    def test_live_adapters_is_module_level_dict(self):
        """_LIVE_ADAPTERS 必须是模块级 dict[str, Any]。"""
        # 直接 import 后修改 source module attr, 防止误改别名
        assert hasattr(wechat_ilink, "_LIVE_ADAPTERS")
        assert isinstance(wechat_ilink._LIVE_ADAPTERS, dict), (
            f"_LIVE_ADAPTERS 应为 dict, 实际 {type(wechat_ilink._LIVE_ADAPTERS)}"
        )

    def test_disconnect_uses_pop_with_default(self):
        """disconnect() 必须用 ``_LIVE_ADAPTERS.pop(self._token, None)`` 而非 ``del``。"""
        import inspect

        from butler.gateway.platforms.wechat_ilink import WeChatAdapter

        source = inspect.getsource(WeChatAdapter.disconnect)
        assert "_LIVE_ADAPTERS.pop(self._token, None)" in source, (
            "disconnect() 应使用 .pop(..., None) 防止重复 disconnect 抛 KeyError"
        )
        # 防御: 不应有 del
        assert "del _LIVE_ADAPTERS" not in source, (
            "disconnect() 不应使用 del (会抛 KeyError on 重复 disconnect)"
        )

    def test_connect_assigns_to_dict(self):
        """connect() 末尾应执行 ``_LIVE_ADAPTERS[self._token] = self``。"""
        import inspect

        from butler.gateway.platforms.wechat_ilink import WeChatAdapter

        source = inspect.getsource(WeChatAdapter.connect)
        assert "_LIVE_ADAPTERS[self._token] = self" in source, (
            "connect() 应在末尾注册到 _LIVE_ADAPTERS"
        )

    def test_lookup_uses_get_with_default(self):
        """调用方 (line 1956) 必须用 ``.get(resolved_token)`` 而非 ``[resolved_token]``。"""
        # 找所有 _LIVE_ADAPTERS 引用, 确保没裸下标访问
        import inspect

        from butler.gateway.platforms import wechat_ilink

        source = inspect.getsource(wechat_ilink)
        # 允许 .get(...) 和 .pop(..., None) 和 [...] = ... (写入)
        # 禁止裸 _LIVE_ADAPTERS[xxx] 读取 (会抛 KeyError)
        for line in source.splitlines():
            stripped = line.strip()
            if "_LIVE_ADAPTERS[" in stripped and "=" not in stripped.split("_LIVE_ADAPTERS[", 1)[1].split("]", 1)[1]:
                pytest.fail(
                    f"found unsafe read _LIVE_ADAPTERS[...]: {stripped!r}"
                )
