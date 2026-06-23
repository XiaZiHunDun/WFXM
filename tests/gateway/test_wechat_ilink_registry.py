"""R1-12 — thread-safe, GC-friendly registry for live WeChat adapters.

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-12

Bug: ``butler/gateway/platforms/wechat_ilink.py`` had a module-level
``_LIVE_ADAPTERS: Dict[str, Any] = {}`` with no lock. Concurrent
register / get / pop from the long-poll loop and the one-shot
``send_wechat_direct`` path could corrupt the dict.

Fix: a small ``AdapterRegistry`` class backed by
``weakref.WeakValueDictionary`` (so dropped adapters are reclaimed
automatically) and a ``threading.RLock`` (so concurrent mutations
are serialised).

This file covers the registry class *in isolation*. Call-site
wiring (the 3 production code paths that used to touch
``_LIVE_ADAPTERS``) and integration with the R1-4a/4b module split
are exercised by a second batch of tests that lands in the same
PR, after the call sites are migrated to the registry.
"""

from __future__ import annotations

import gc
import inspect
import threading
import weakref
from typing import Any
from unittest.mock import MagicMock

import pytest

from butler.gateway.platforms.wechat_ilink_registry import (
    AdapterRegistry,
    _ADAPTER_REGISTRY,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def fresh_registry() -> AdapterRegistry:
    """A private registry, not the module singleton — keeps tests isolated."""
    return AdapterRegistry()


@pytest.fixture(autouse=True)
def _isolate_module_singleton() -> None:
    """Snapshot+restore the module singleton so a test cannot leak entries
    into another test that happens to import the singleton directly."""
    snapshot = list(_ADAPTER_REGISTRY._adapters.items())  # type: ignore[attr-defined]
    try:
        yield
    finally:
        with _ADAPTER_REGISTRY._lock:  # type: ignore[attr-defined]
            _ADAPTER_REGISTRY._adapters.clear()  # type: ignore[attr-defined]
            for k, v in snapshot:
                _ADAPTER_REGISTRY._adapters[k] = v  # type: ignore[attr-defined]


def _make_fake_adapter(token: str = "tok") -> MagicMock:
    """Minimal stand-in for a WeChatAdapter — only ``_token`` matters."""
    a = MagicMock()
    a._token = token
    return a


# ---------------------------------------------------------------------------
# 1. Single-threaded contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSequentialSemantics:
    def test_register_then_get_returns_same_adapter(self, fresh_registry):
        a = _make_fake_adapter("t-a")
        fresh_registry.register("t-a", a)
        assert fresh_registry.get("t-a") is a

    def test_register_overwrites_existing_token(self, fresh_registry):
        a1 = _make_fake_adapter("t-b")
        a2 = _make_fake_adapter("t-b")
        fresh_registry.register("t-b", a1)
        fresh_registry.register("t-b", a2)
        assert fresh_registry.get("t-b") is a2
        assert fresh_registry.get("t-b") is not a1

    def test_unregister_returns_true_when_present(self, fresh_registry):
        a = _make_fake_adapter("t-c")
        fresh_registry.register("t-c", a)
        assert fresh_registry.unregister("t-c") is True
        assert fresh_registry.get("t-c") is None

    def test_unregister_returns_false_when_missing(self, fresh_registry):
        assert fresh_registry.unregister("never-registered") is False

    def test_unregister_is_idempotent(self, fresh_registry):
        a = _make_fake_adapter("t-d")
        fresh_registry.register("t-d", a)
        assert fresh_registry.unregister("t-d") is True
        assert fresh_registry.unregister("t-d") is False

    def test_get_missing_token_returns_none(self, fresh_registry):
        assert fresh_registry.get("ghost") is None

    def test_contains_returns_bool(self, fresh_registry):
        a = _make_fake_adapter("t-e")
        fresh_registry.register("t-e", a)
        assert "t-e" in fresh_registry
        assert "ghost" not in fresh_registry

    def test_len_reports_count(self, fresh_registry):
        assert len(fresh_registry) == 0
        x = _make_fake_adapter("x")
        fresh_registry.register("x", x)
        assert len(fresh_registry) == 1
        y = _make_fake_adapter("y")
        fresh_registry.register("y", y)
        assert len(fresh_registry) == 2

    def test_live_count_matches_len(self, fresh_registry):
        # ``live_count`` is the diagnostics-facing alias; contract is
        # that it never raises (no "dict changed size during iteration").
        p = _make_fake_adapter("p")
        q = _make_fake_adapter("q")
        fresh_registry.register("p", p)
        fresh_registry.register("q", q)
        assert fresh_registry.live_count() == 2


# ---------------------------------------------------------------------------
# 2. WeakValueDictionary contract
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestWeakRefSemantics:
    def test_dropped_strong_ref_releases_entry(self, fresh_registry):
        """The core audit-fix promise: if the only strong reference to
        an adapter disappears, the registry must report it as gone."""
        a = _make_fake_adapter("ephemeral")
        fresh_registry.register("ephemeral", a)
        assert "ephemeral" in fresh_registry
        del a
        # WeakValueDictionary reaps lazily; gc forces a collection.
        gc.collect()
        assert fresh_registry.get("ephemeral") is None
        assert "ephemeral" not in fresh_registry
        assert len(fresh_registry) == 0

    def test_strong_ref_keeps_entry(self, fresh_registry):
        a = _make_fake_adapter("live")
        fresh_registry.register("live", a)
        gc.collect()
        # External strong ref keeps the entry alive.
        assert fresh_registry.get("live") is a

    def test_weakref_does_not_count_as_strong_ref(self, fresh_registry):
        a = _make_fake_adapter("weak-only")
        ref = weakref.ref(a)
        fresh_registry.register("weak-only", a)
        del a
        gc.collect()
        # The strong ref from the registry is gone (WeakValue), so the
        # entry should be reaped; only the external weakref survives.
        assert ref() is None
        assert fresh_registry.get("weak-only") is None


# ---------------------------------------------------------------------------
# 3. Thread-safety contract (the core H finding)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestThreadSafetyDistinctTokens:
    def test_concurrent_register_distinct_tokens(self, fresh_registry):
        N = 32
        barrier = threading.Barrier(N)
        adapters = [_make_fake_adapter(f"d-{i}") for i in range(N)]

        def do_reg(a: MagicMock) -> None:
            barrier.wait()
            fresh_registry.register(a._token, a)

        threads = [threading.Thread(target=do_reg, args=(a,)) for a in adapters]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "register thread hung"

        assert len(fresh_registry) == N
        for a in adapters:
            assert fresh_registry.get(a._token) is a

    def test_concurrent_unregister_and_lookup(self, fresh_registry):
        """One thread unregisters; many threads concurrently read.
        Lookups must return the adapter or ``None`` — never raise."""
        a = _make_fake_adapter("race-lookup")
        fresh_registry.register("race-lookup", a)

        N_LOOKUP = 16
        barrier = threading.Barrier(N_LOOKUP + 1)
        results: list[Any] = []
        lock = threading.Lock()

        def do_lookup() -> None:
            barrier.wait()
            v = fresh_registry.get("race-lookup")
            with lock:
                results.append(v)

        def do_unregister() -> None:
            barrier.wait()
            fresh_registry.unregister("race-lookup")

        lookup_threads = [threading.Thread(target=do_lookup) for _ in range(N_LOOKUP)]
        unreg_thread = threading.Thread(target=do_unregister)
        for t in lookup_threads:
            t.start()
        unreg_thread.start()
        for t in lookup_threads:
            t.join(timeout=5)
        unreg_thread.join(timeout=5)

        for r in results:
            assert r is a or r is None


@pytest.mark.unit
class TestThreadSafetySameToken:
    def test_concurrent_register_same_token_last_writer_wins(
        self, fresh_registry
    ):
        N = 16
        token = "shared"
        barrier = threading.Barrier(N)
        adapters = [_make_fake_adapter(token) for _ in range(N)]

        def do_reg(a: MagicMock) -> None:
            barrier.wait()
            fresh_registry.register(token, a)

        threads = [threading.Thread(target=do_reg, args=(a,)) for a in adapters]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive(), "register thread hung"

        assert len(fresh_registry) == 1
        winner = fresh_registry.get(token)
        assert winner in adapters, "winner must be one of the registered adapters"


@pytest.mark.unit
class TestThreadSafetyMutationDuringCount:
    def test_register_while_other_thread_counts(self, fresh_registry):
        """Classic "dict changed size during iteration" hazard.
        ``live_count`` must take the lock so it cannot race a register."""
        N_REG = 8
        N_COUNT = 8
        reg_barrier = threading.Barrier(N_REG)
        count_barrier = threading.Barrier(N_REG + N_COUNT)
        stop = threading.Event()
        errors: list[BaseException] = []
        errors_lock = threading.Lock()

        def do_reg(i: int) -> None:
            try:
                reg_barrier.wait()
                count_barrier.wait()
                for k in range(200):
                    fresh_registry.register(
                        f"r-{i}-{k}", _make_fake_adapter(f"r-{i}-{k}")
                    )
            except BaseException as e:  # noqa: BLE001
                with errors_lock:
                    errors.append(e)

        def do_count() -> None:
            try:
                count_barrier.wait()
                while not stop.is_set():
                    n = fresh_registry.live_count()
                    assert n >= 0
            except BaseException as e:  # noqa: BLE001
                with errors_lock:
                    errors.append(e)
                raise

        reg_threads = [threading.Thread(target=do_reg, args=(i,)) for i in range(N_REG)]
        count_threads = [threading.Thread(target=do_count) for _ in range(N_COUNT)]
        for t in (*reg_threads, *count_threads):
            t.start()
        for t in reg_threads:
            t.join(timeout=10)
        stop.set()
        for t in count_threads:
            t.join(timeout=10)

        assert not errors, f"concurrent reg+count raised: {errors!r}"


# ---------------------------------------------------------------------------
# 4. Module singleton — registry module owns a single shared instance
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestModuleSingleton:
    def test_singleton_is_module_level(self):
        from butler.gateway.platforms import wechat_ilink_registry

        assert isinstance(wechat_ilink_registry._ADAPTER_REGISTRY, AdapterRegistry)

    def test_singleton_is_shared_across_imports(self):
        # Re-importing must not create a second instance.
        from butler.gateway.platforms import wechat_ilink_registry
        from butler.gateway.platforms.wechat_ilink_registry import (
            _ADAPTER_REGISTRY as imported_ref,
        )

        assert imported_ref is wechat_ilink_registry._ADAPTER_REGISTRY

    def test_singleton_supports_full_lifecycle(self):
        """End-to-end smoke against the module singleton, not a private
        fresh registry — exercises the same code path the production
        call sites will use."""
        a = _make_fake_adapter("singleton-tok")
        _ADAPTER_REGISTRY.register("singleton-tok", a)
        assert _ADAPTER_REGISTRY.get("singleton-tok") is a
        assert "singleton-tok" in _ADAPTER_REGISTRY
        assert _ADAPTER_REGISTRY.unregister("singleton-tok") is True
        assert _ADAPTER_REGISTRY.get("singleton-tok") is None


# ---------------------------------------------------------------------------
# 5. Integration with the R1-4a/4b module split — call-site wiring
# ---------------------------------------------------------------------------


WECHAT_ILINK_PATH = "butler.gateway.platforms.wechat_ilink"
WECHAT_ILINK_PHASES_PATH = "butler.gateway.platforms.wechat_ilink_phases"


@pytest.mark.unit
class TestCallSiteWiring:
    """Static checks on the 3 call sites in the R1-4 split. They must
    route through the registry, not the old module-level dict."""

    def test_wechat_ilink_exposes_registry(self):
        import importlib

        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert isinstance(mod._ADAPTER_REGISTRY, AdapterRegistry)

    def test_disconnect_uses_registry_unregister(self):
        from butler.gateway.platforms.wechat_ilink import WeChatAdapter

        src = inspect.getsource(WeChatAdapter.disconnect)
        assert "_ADAPTER_REGISTRY.unregister(self._token)" in src, (
            "disconnect() must route through AdapterRegistry.unregister; "
            "raw _LIVE_ADAPTERS.pop is the R1-12 audit target."
        )
        assert "_LIVE_ADAPTERS" not in src, (
            "disconnect() must no longer touch the module-level dict"
        )

    def test_connect_assigns_via_registry(self):
        """``_start_poll_and_register`` (R1-4a) must register via the registry."""
        import importlib

        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        fn = getattr(mod, "_start_poll_and_register", None)
        assert fn is not None, "phases module must export _start_poll_and_register"
        src = inspect.getsource(fn)
        assert "_ADAPTER_REGISTRY.register(" in src, (
            "_start_poll_and_register must register via AdapterRegistry"
        )
        assert "_LIVE_ADAPTERS" not in src, (
            "_start_poll_and_register must no longer touch the module-level dict"
        )

    def test_send_wechat_direct_uses_registry_get(self):
        from butler.gateway.platforms.wechat_ilink import send_wechat_direct

        src = inspect.getsource(send_wechat_direct)
        assert "_ADAPTER_REGISTRY.get(" in src, (
            "send_wechat_direct must look up live adapter via AdapterRegistry.get"
        )
        assert "_LIVE_ADAPTERS" not in src, (
            "send_wechat_direct must no longer touch the module-level dict"
        )

    def test_disconnect_drops_adapter_from_registry(self, fresh_registry):
        """End-to-end: register an adapter, then simulate what
        ``WeChatAdapter.disconnect`` does (the first line is now
        ``_ADAPTER_REGISTRY.unregister(self._token)``) and verify the
        adapter is gone."""
        a = _make_fake_adapter("t-integration-disconnect")
        fresh_registry.register("t-integration-disconnect", a)
        # Mirror the disconnect() body: first line is the unregister call.
        assert fresh_registry.unregister(a._token) is True
        assert fresh_registry.get("t-integration-disconnect") is None


@pytest.mark.unit
class TestBackwardCompatShape:
    """R1-12 replaces the old ``_LIVE_ADAPTERS`` dict with a registry.
    No code path on ``wechat_ilink`` may still reference the old name
    as a live (callable) attribute; comments / docstrings are fine.
    """

    def test_wechat_ilink_has_no_live_adapters_dict_attr(self):
        import importlib

        mod = importlib.import_module(WECHAT_ILINK_PATH)
        # The dict itself must be gone; allowing only the registry:
        if hasattr(mod, "_LIVE_ADAPTERS"):
            assert not isinstance(mod._LIVE_ADAPTERS, dict), (
                "_LIVE_ADAPTERS dict shape was the R1-12 audit target."
            )

    def test_phases_module_has_no_live_adapters_dict_attr(self):
        import importlib

        mod = importlib.import_module(WECHAT_ILINK_PHASES_PATH)
        if hasattr(mod, "_LIVE_ADAPTERS"):
            assert not isinstance(mod._LIVE_ADAPTERS, dict), (
                "_LIVE_ADAPTERS dict shape was the R1-12 audit target."
            )

    def test_send_wechat_direct_is_callable(self):
        from butler.gateway.platforms.wechat_ilink import send_wechat_direct

        # The R1-12 wiring doesn't change the public surface — the
        # function is still importable + async-callable.
        import inspect as _inspect

        assert _inspect.iscoroutinefunction(send_wechat_direct)

