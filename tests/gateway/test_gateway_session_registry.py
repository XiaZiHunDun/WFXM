from __future__ import annotations

import threading
import time
from unittest.mock import MagicMock

from butler.gateway.session_registry import GatewaySessionRegistry


def test_registry_reuses_loop_and_tracks_activity():
    now = {"value": 10.0}
    created: list[str] = []

    def factory(session_key: str):
        created.append(session_key)
        return MagicMock(name=f"loop-{session_key}")  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade

    registry = GatewaySessionRegistry(factory, now=lambda: now["value"])

    first = registry.get_or_create("s1")
    now["value"] = 12.0
    second = registry.get_or_create("s1")

    assert first is second
    assert created == ["s1"]
    assert registry.last_active_at("s1") == 12.0


def test_reset_clears_tool_audit_for_removed_session():
    from butler.execution_context import use_execution_context
    from butler.tools.registry import dispatch_tool, get_tool_audit_events, reset_tool_audit_events
    from types import SimpleNamespace

    reset_tool_audit_events()
    orch = SimpleNamespace()
    registry = GatewaySessionRegistry(
        lambda key: MagicMock(name=f"loop-{key}"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        on_session_removed=reset_tool_audit_events,
    )

    with use_execution_context(orch, session_key="alice"):
        dispatch_tool("missing_tool", {})
    with use_execution_context(orch, session_key="bob"):
        dispatch_tool("missing_tool", {})

    registry.get_or_create("alice")
    registry.get_or_create("bob")
    registry.reset("alice")

    assert get_tool_audit_events(session_key="alice") == []
    assert len(get_tool_audit_events(session_key="bob")) == 1


def test_reset_finalizes_only_target_session():
    loops = {"s1": MagicMock(name="s1"), "s2": MagicMock(name="s2")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
    )
    registry.get_or_create("s1")
    registry.get_or_create("s2")
    registry.set_health("s1", {"stale": True})
    registry.set_health("s2", {"keep": True})

    registry.reset("s1")

    assert finalized == [loops["s1"]]
    assert "s1" not in registry.sessions
    assert "s2" in registry.sessions
    assert registry.get_health("s1") == {}
    assert registry.get_health("s2") == {"keep": True}


def test_reset_sessions_for_chat_clears_all_project_loops():
    loops = {
        "wechat:u1:alpha": MagicMock(name="alpha"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        "wechat:u1:beta": MagicMock(name="beta"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        "wechat:u2:alpha": MagicMock(name="other-chat"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    }
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
    )
    for key in loops:
        registry.get_or_create(key)

    cleared = registry.reset_sessions_for_chat(platform="wechat", chat_id="u1")

    assert set(cleared) == {"wechat:u1:alpha", "wechat:u1:beta"}
    assert "wechat:u1:alpha" not in registry.sessions
    assert "wechat:u1:beta" not in registry.sessions
    assert "wechat:u2:alpha" in registry.sessions
    assert len(finalized) == 2


def test_evict_idle_clears_tool_audit_for_removed_session():
    from butler.execution_context import use_execution_context
    from butler.tools.registry import dispatch_tool, get_tool_audit_events, reset_tool_audit_events
    from types import SimpleNamespace

    reset_tool_audit_events()
    now = {"value": 100.0}
    orch = SimpleNamespace()
    registry = GatewaySessionRegistry(
        lambda key: MagicMock(name=f"loop-{key}"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        finalize=lambda loop: None,
        idle_ttl_seconds=30,
        now=lambda: now["value"],
        on_session_removed=reset_tool_audit_events,
    )

    with use_execution_context(orch, session_key="idle"):
        dispatch_tool("missing_tool", {})
    with use_execution_context(orch, session_key="active"):
        dispatch_tool("missing_tool", {})

    registry.get_or_create("idle")
    now["value"] = 140.0
    registry.get_or_create("active")
    registry.evict_idle()

    assert get_tool_audit_events(session_key="idle") == []
    assert len(get_tool_audit_events(session_key="active")) == 1


def test_evict_idle_finalizes_expired_sessions_only():
    now = {"value": 100.0}
    loops = {"active": MagicMock(name="active"), "idle": MagicMock(name="idle")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
        idle_ttl_seconds=30,
        now=lambda: now["value"],
    )

    registry.get_or_create("idle")
    now["value"] = 140.0
    registry.get_or_create("active")
    evicted = registry.evict_idle()

    assert evicted == ["idle"]
    assert finalized == [loops["idle"]]
    assert set(registry.sessions) == {"active"}


def test_lru_eviction_clears_tool_audit_for_removed_session():
    from butler.execution_context import use_execution_context
    from butler.tools.registry import dispatch_tool, get_tool_audit_events, reset_tool_audit_events
    from types import SimpleNamespace

    reset_tool_audit_events()
    now = {"value": 0.0}
    orch = SimpleNamespace()
    registry = GatewaySessionRegistry(
        lambda key: MagicMock(name=f"loop-{key}"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        max_sessions=2,
        now=lambda: now["value"],
        on_session_removed=reset_tool_audit_events,
    )

    with use_execution_context(orch, session_key="a"):
        dispatch_tool("missing_tool", {})
    with use_execution_context(orch, session_key="b"):
        dispatch_tool("missing_tool", {})
    with use_execution_context(orch, session_key="c"):
        dispatch_tool("missing_tool", {})

    for key in ("a", "b", "c"):
        now["value"] += 1.0
        registry.get_or_create(key)

    assert get_tool_audit_events(session_key="a") == []
    assert len(get_tool_audit_events(session_key="b")) == 1
    assert len(get_tool_audit_events(session_key="c")) == 1


def test_lru_limit_evicts_oldest_session():
    now = {"value": 0.0}
    loops = {key: MagicMock(name=key) for key in ("a", "b", "c")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
        max_sessions=2,
        now=lambda: now["value"],
    )

    for key in ("a", "b", "c"):
        now["value"] += 1.0
        registry.get_or_create(key)

    assert set(registry.sessions) == {"b", "c"}
    assert finalized == [loops["a"]]
    assert "a" not in registry._session_locks


def test_lru_does_not_evict_active_session():
    now = {"value": 0.0}
    loops = {key: MagicMock(name=key) for key in ("active", "new")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
        max_sessions=1,
        now=lambda: now["value"],
    )
    registry.get_or_create("active")
    registry.mark_active("active")
    now["value"] = 10.0

    registry.mark_active("new")
    registry.get_or_create("new")

    assert set(registry.sessions) == {"active", "new"}
    assert finalized == []
    registry.mark_inactive("new")
    registry.mark_inactive("active")
    assert registry.enforce_lru() == ["active"]
    assert finalized == [loops["active"]]


def test_idle_eviction_skips_active_session():
    now = {"value": 0.0}
    loop = MagicMock(name="active")  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    registry = GatewaySessionRegistry(
        lambda key: loop,
        idle_ttl_seconds=10,
        now=lambda: now["value"],
    )
    registry.get_or_create("active")
    registry.mark_active("active")
    now["value"] = 99.0

    assert registry.evict_idle() == []
    assert "active" in registry.sessions


def test_idle_eviction_rechecks_last_active_before_reset():
    now = {"value": 0.0}
    loops = {key: MagicMock(name=key) for key in ("old", "other")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
        idle_ttl_seconds=10,
        now=lambda: now["value"],
    )
    registry.get_or_create("old")
    now["value"] = 99.0
    registry.get_or_create("other")

    now["value"] = 100.0
    registry.touch("old")
    assert registry.evict_idle() == []

    assert "old" in registry.sessions
    assert finalized == []


def test_reset_all_clears_tool_audit_for_all_sessions():
    from butler.execution_context import use_execution_context
    from butler.tools.registry import dispatch_tool, get_tool_audit_events, reset_tool_audit_events
    from types import SimpleNamespace

    reset_tool_audit_events()
    orch = SimpleNamespace()
    registry = GatewaySessionRegistry(
        lambda key: MagicMock(name=f"loop-{key}"),  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        on_session_removed=reset_tool_audit_events,
    )

    with use_execution_context(orch, session_key="alice"):
        dispatch_tool("missing_tool", {})
    with use_execution_context(orch, session_key="bob"):
        dispatch_tool("missing_tool", {})

    registry.get_or_create("alice")
    registry.get_or_create("bob")
    registry.reset_all()

    assert get_tool_audit_events() == []


def test_reset_all_finalizes_every_session():
    loops = {key: MagicMock(name=key) for key in ("a", "b")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    finalized: list[object] = []
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        finalize=lambda loop: finalized.append(loop),
    )
    registry.get_or_create("a")
    registry.get_or_create("b")

    registry.reset_all()

    assert finalized == [loops["a"], loops["b"]]
    assert registry.sessions == {}


def test_direct_session_dict_mutation_tracks_activity():
    now = {"value": 42.0}
    registry = GatewaySessionRegistry(lambda key: MagicMock(), now=lambda: now["value"])  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade

    registry.sessions["manual"] = MagicMock()  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade

    assert registry.last_active_at("manual") == 42.0


def test_concurrent_get_or_create_creates_one_loop_per_session():
    created: list[object] = []

    def factory(_key: str):
        time.sleep(0.02)
        loop = MagicMock()  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
        created.append(loop)
        return loop

    registry = GatewaySessionRegistry(factory)
    results: list[object] = []

    threads = [
        threading.Thread(target=lambda: results.append(registry.get_or_create("same")))
        for _ in range(2)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert len(created) == 1
    assert results[0] is results[1]


def test_reset_all_blocks_new_sessions_until_reset_finishes():
    loops = {key: MagicMock(name=key) for key in ("old", "new")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    registry = GatewaySessionRegistry(lambda key: loops[key])
    registry.get_or_create("old")
    old_lock = registry.session_lock("old")
    old_lock.acquire()
    registry.mark_active("old")
    reset_done = threading.Event()
    created_new = threading.Event()

    def _reset_all():
        registry.reset_all()
        reset_done.set()

    def _create_new():
        registry.get_or_create("new")
        created_new.set()

    reset_thread = threading.Thread(target=_reset_all)
    reset_thread.start()
    time.sleep(0.02)
    create_thread = threading.Thread(target=_create_new)
    create_thread.start()
    time.sleep(0.02)

    assert not reset_done.is_set()
    assert not created_new.is_set()

    registry.mark_inactive("old")
    old_lock.release()
    reset_thread.join(timeout=1)
    create_thread.join(timeout=1)

    assert reset_done.is_set()
    assert created_new.is_set()
    assert set(registry.sessions) == {"new"}


def test_evict_idle_is_noop_while_reset_all_waits_for_active_session():
    now = {"value": 0.0}
    loops = {key: MagicMock(name=key) for key in ("active", "idle")}  # noqa: magicmock-no-spec — SessionRegistry / AgentLoop facade
    registry = GatewaySessionRegistry(
        lambda key: loops[key],
        idle_ttl_seconds=10,
        now=lambda: now["value"],
    )
    registry.get_or_create("active")
    registry.get_or_create("idle")
    registry.mark_active("active")
    now["value"] = 99.0
    reset_started = threading.Event()
    reset_done = threading.Event()

    def _reset_all():
        reset_started.set()
        registry.reset_all()
        reset_done.set()

    reset_thread = threading.Thread(target=_reset_all)
    reset_thread.start()
    reset_started.wait(timeout=1)
    time.sleep(0.02)

    assert not reset_done.is_set()
    assert registry.evict_idle() == []

    registry.mark_inactive("active")
    reset_thread.join(timeout=1)

    assert reset_done.is_set()
    assert registry.sessions == {}
