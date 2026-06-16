"""R4-8..R4-15: audit tail concurrency / thread-safety fixes."""

from __future__ import annotations

import asyncio
import inspect
import threading
import time
from unittest.mock import patch

import pytest

from butler.core import message_ir
from butler.gateway import session_lifecycle as gw_session
from butler.gateway.platforms.wechat_ilink_utils import ContextTokenStore
from butler.mcp import async_runner
from butler.runtime import notify
from butler.transport import providers, stream_probe


@pytest.fixture(autouse=True)
def _reset_gateway_session_state():
    with gw_session._LOCK:
        gw_session._WARMED.clear()
    yield
    with gw_session._LOCK:
        gw_session._WARMED.clear()


@pytest.fixture(autouse=True)
def _reset_stream_probe():
    with stream_probe._PROBE_LOCK:
        stream_probe._LAST_PROBE.clear()
    yield
    with stream_probe._PROBE_LOCK:
        stream_probe._LAST_PROBE.clear()


# ── R4-8: try_enter_session warms once under contention ─────────────────


@pytest.mark.unit
def test_try_enter_session_warms_once(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_SESSION_INITIALIZING", "1")
    calls: list[str] = []
    barrier = threading.Barrier(4)

    def warmup() -> None:
        calls.append("warm")
        time.sleep(0.05)

    def worker() -> None:
        barrier.wait(timeout=5)
        gw_session.try_enter_session("sk-r4-8", warmup)

    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=10)
        assert not t.is_alive()
    assert calls == ["warm"], f"expected single warmup, got {calls!r}"


# ── R4-9: shutdown keeps globals until thread joins ─────────────────────


@pytest.mark.unit
def test_shutdown_timeout_keeps_globals_until_join(monkeypatch):
    saved_loop = async_runner._loop
    saved_thread = async_runner._thread
    async_runner._loop = None
    async_runner._thread = None
    try:
        loop = async_runner._ensure_loop()
        thread = async_runner._thread
        assert thread is not None

        with patch.object(thread, "join", return_value=None):
            with patch.object(thread, "is_alive", return_value=True):
                ok = async_runner.shutdown_async_runner(timeout=0.01)

        assert ok is False
        assert async_runner._loop is loop
        assert async_runner._thread is thread
    finally:
        try:
            async_runner.shutdown_async_runner(timeout=2.0)
        except Exception:
            pass
        async_runner._loop = saved_loop
        async_runner._thread = saved_thread


# ── R4-10: cooldown sleep rejects running event loop ────────────────────


@pytest.mark.unit
def test_wait_push_cooldown_rejects_sleep_from_async_loop(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "25")
    notify._write_last_push_monotonic(time.monotonic())

    async def _driver() -> None:
        notify._wait_push_cooldown()

    loop = asyncio.new_event_loop()
    try:
        with pytest.raises(RuntimeError, match="must not be called from a running event loop"):
            loop.run_until_complete(_driver())
    finally:
        loop.close()


@pytest.mark.unit
def test_wait_push_cooldown_no_sleep_ok_from_async_loop(butler_home_push, monkeypatch):
    monkeypatch.setenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "0")

    async def _driver() -> float:
        return notify._wait_push_cooldown()

    loop = asyncio.new_event_loop()
    try:
        assert loop.run_until_complete(_driver()) == 0.0
    finally:
        loop.close()


# ── R4-11: signal fallback does not call request_stop directly ──────────


@pytest.mark.unit
def test_signal_fallback_avoids_direct_request_stop():
    from butler.gateway import runner

    source = inspect.getsource(runner.run_gateway_async)
    assert "signal.signal(sig, lambda *_: request_stop(stop))" not in source
    assert "call_soon_threadsafe(stop.set)" in source


# ── R4-12: stream_probe last snapshot under contention ──────────────────


@pytest.mark.unit
def test_stream_probe_concurrent_updates():
    errors: list[BaseException] = []
    lock = threading.Lock()
    stop = threading.Event()

    def writer(i: int) -> None:
        try:
            while not stop.is_set():
                with stream_probe._PROBE_LOCK:
                    stream_probe._LAST_PROBE.clear()
                    stream_probe._LAST_PROBE.update({"ok": True, "seq": i})
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    def reader() -> None:
        try:
            while not stop.is_set():
                snap = stream_probe.last_stream_probe()
                assert isinstance(snap, dict)
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(3)]
    threads.append(threading.Thread(target=reader))
    for t in threads:
        t.start()
    stop.set()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert not errors, f"stream_probe race: {errors!r}"


# ── R4-13: ContextTokenStore thread-safe cache ──────────────────────────


@pytest.mark.unit
def test_context_token_store_concurrent(tmp_path):
    store = ContextTokenStore(str(tmp_path))
    errors: list[BaseException] = []
    lock = threading.Lock()
    stop = threading.Event()

    def worker(i: int) -> None:
        try:
            uid = f"u{i % 3}"
            while not stop.is_set():
                store.set("acct", uid, f"tok-{i}")
                assert store.get("acct", uid) == f"tok-{i}"
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in threads:
        t.start()
    stop.set()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert not errors, f"context token store race: {errors!r}"


# ── R4-14: message_ir converter registry lock ───────────────────────────


@pytest.mark.unit
def test_message_ir_register_concurrent():
    errors: list[BaseException] = []
    lock = threading.Lock()
    stop = threading.Event()

    def registrar(i: int) -> None:
        try:
            while not stop.is_set():

                def _conv(_p: object, n=i) -> message_ir.CanonicalMessage:
                    return message_ir.CanonicalMessage(role="user", blocks=[], channel=f"c{n}")

                message_ir.register_converter(f"ch{i % 5}", _conv)
                message_ir.convert_inbound(f"ch{i % 5}", "hi")
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    threads = [threading.Thread(target=registrar, args=(i,)) for i in range(5)]
    for t in threads:
        t.start()
    stop.set()
    for t in threads:
        t.join(timeout=5)
        assert not t.is_alive()
    assert not errors, f"message_ir race: {errors!r}"


# ── R4-15: provider registry lock ───────────────────────────────────────


@pytest.mark.unit
def test_provider_registry_concurrent():
    orig_registry = dict(providers._REGISTRY)
    orig_aliases = dict(providers._ALIASES)
    errors: list[BaseException] = []
    lock = threading.Lock()
    stop = threading.Event()

    def worker(i: int) -> None:
        try:
            while not stop.is_set():
                name = f"prov-{i % 4}"
                providers.register_provider(
                    providers.ProviderProfile(name=name, aliases=(f"alias-{i}",))
                )
                assert providers.get_provider(name) is not None
                providers.list_providers()
        except BaseException as exc:  # noqa: BLE001
            with lock:
                errors.append(exc)

    try:
        threads = [threading.Thread(target=worker, args=(i,)) for i in range(4)]
        for t in threads:
            t.start()
        stop.set()
        for t in threads:
            t.join(timeout=5)
            assert not t.is_alive()
        assert not errors, f"providers race: {errors!r}"
    finally:
        with providers._REGISTRY_LOCK:
            providers._REGISTRY.clear()
            providers._REGISTRY.update(orig_registry)
            providers._ALIASES.clear()
            providers._ALIASES.update(orig_aliases)


@pytest.fixture
def butler_home_push(tmp_path, monkeypatch):
    bh = tmp_path / "bh"
    bh.mkdir()
    monkeypatch.setenv("BUTLER_HOME", str(bh))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    return bh
