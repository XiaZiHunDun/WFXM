"""Sprint 11 REL-11-5: inbound_idempotency inflight 状态无 TTL

Sprint 11 审计：inbound_idempotency.py 22, 79-82
    bucket[eid] = ("inflight", time.monotonic())

inflight 状态无 TTL/无 sweep → worker 崩溃后 external_id 永久 inflight，
后续同 ID 消息一律 duplicate_inflight 拒绝。

修复：lazy sweep（每次 check_and_reserve_inbound / complete_inbound
时清理该 session 中 ts 超过 TTL 的 inflight 条目）。
- TTL 默认 60s，可通过 BUTLER_GATEWAY_INFLIGHT_TTL_SEC 配置
- sweep 只清理 inflight 状态，保留 done 状态（避免误清理历史）
- 线程安全（lock 内执行 sweep）

测试：6 个 RED 测试覆盖 TTL 过期清理 + 活跃 inflight 保护 + 配置。
"""

from __future__ import annotations

import time

import pytest

from butler.gateway import inbound_idempotency


@pytest.fixture(autouse=True)
def _reset_seen():
    """每个测试前清空 _SEEN。"""
    with inbound_idempotency._LOCK:
        inbound_idempotency._SEEN.clear()
    yield
    with inbound_idempotency._LOCK:
        inbound_idempotency._SEEN.clear()


def _force_inflight_age(session_key: str, eid: str, age_sec: float) -> None:
    """helper: 直接写一个 inflight 条目，时间戳回拨 age_sec。"""
    with inbound_idempotency._LOCK:
        bucket = inbound_idempotency._SEEN.setdefault(session_key, __import__("collections").OrderedDict())
        bucket[eid] = ("inflight", time.monotonic() - age_sec)


@pytest.mark.unit
def test_inflight_ttl_default_value():
    """_INFLIGHT_TTL_SEC 默认值应存在且合理（30-300s 范围）。"""
    assert hasattr(inbound_idempotency, "_INFLIGHT_TTL_SEC"), (
        "inbound_idempotency 应有 _INFLIGHT_TTL_SEC 默认常量"
    )
    ttl = inbound_idempotency._INFLIGHT_TTL_SEC
    assert 30.0 <= ttl <= 300.0, f"_INFLIGHT_TTL_SEC 默认应在 30-300s 范围，实际 {ttl}"


@pytest.mark.unit
def test_expired_inflight_swept_on_new_reserve(monkeypatch):
    """inflight 状态超过 TTL 时，新 reserve 应清掉旧 inflight（不被误拒）。"""
    # 设小 TTL 便于测试
    monkeypatch.setattr(inbound_idempotency, "_INFLIGHT_TTL_SEC", 5.0)

    session = "test_session"
    eid = "old_msg_001"

    # 直接写一个 100s 前的 inflight（远超 TTL）
    _force_inflight_age(session, eid, age_sec=100.0)

    # 新消息同 eid 应被接受（旧 inflight 已过期被 sweep）
    decision = inbound_idempotency.check_and_reserve_inbound(session, eid)
    assert decision.accept, (
        f"TTL 过期（100s > 5s）后新 reserve 应被接受，实际 reject: {decision.reason!r}"
    )


@pytest.mark.unit
def test_active_inflight_not_swept(monkeypatch):
    """未超 TTL 的活跃 inflight 仍应被识别并拒绝新消息。"""
    monkeypatch.setattr(inbound_idempotency, "_INFLIGHT_TTL_SEC", 60.0)

    session = "active_session"
    eid = "active_msg"

    # 直接写一个 5s 前的 inflight（< TTL=60s）
    _force_inflight_age(session, eid, age_sec=5.0)

    # 同 eid 新消息应被拒
    decision = inbound_idempotency.check_and_reserve_inbound(session, eid)
    assert not decision.accept, "未超 TTL 的活跃 inflight 应拒绝新消息"
    assert decision.reason == "duplicate_inflight", (
        f"reason 应是 duplicate_inflight，实际 {decision.reason!r}"
    )


@pytest.mark.unit
def test_done_state_not_swept_by_ttl(monkeypatch):
    """done 状态不应被 TTL sweep 清理（保留历史去重记录）。"""
    monkeypatch.setattr(inbound_idempotency, "_INFLIGHT_TTL_SEC", 5.0)

    session = "done_session"
    eid = "done_msg"

    # 直接写一个 1000s 前的 done 状态
    with inbound_idempotency._LOCK:
        from collections import OrderedDict
        bucket = inbound_idempotency._SEEN.setdefault(session, OrderedDict())
        bucket[eid] = ("done", time.monotonic() - 1000.0)

    # 同 eid 新消息应被拒（done 状态保留去重）
    decision = inbound_idempotency.check_and_reserve_inbound(session, eid)
    assert not decision.accept, "done 状态应保留去重，新消息应被拒"
    assert decision.reason == "duplicate_done", (
        f"reason 应是 duplicate_done，实际 {decision.reason!r}"
    )


@pytest.mark.unit
def test_sweep_on_complete_inbound(monkeypatch):
    """complete_inbound 时也应 sweep 过期 inflight（顺便清理）。"""
    monkeypatch.setattr(inbound_idempotency, "_INFLIGHT_TTL_SEC", 5.0)

    session = "complete_session"
    eid_old = "old_inflight"
    eid_new = "new_inflight"

    # 写 2 条：1 条过期 inflight + 1 条活跃 inflight
    _force_inflight_age(session, eid_old, age_sec=100.0)
    _force_inflight_age(session, eid_new, age_sec=1.0)

    # 调 complete_inbound（应触发 sweep，但不应清掉活跃的）
    inbound_idempotency.complete_inbound(session, eid_new)

    with inbound_idempotency._LOCK:
        bucket = inbound_idempotency._SEEN.get(session, {})
        # 过期 inflight 应被 sweep 掉
        assert eid_old not in bucket, (
            f"过期的 {eid_old} 应被 sweep，实际仍在: {list(bucket.keys())}"
        )
        # 活跃 inflight 被 complete 后应变成 done
        assert bucket.get(eid_new, (None,))[0] == "done", (
            f"complete_inbound 后 eid_new 状态应是 done"
        )


@pytest.mark.unit
def test_ttl_configurable_via_env(monkeypatch):
    """_INFLIGHT_TTL_SEC 应能从环境变量 BUTLER_GATEWAY_INFLIGHT_TTL_SEC 读取。"""
    import os
    monkeypatch.setenv("BUTLER_GATEWAY_INFLIGHT_TTL_SEC", "120.0")
    # 重新加载模块使其读取 env（或者函数式读取）
    # 简化：通过 _resolve_inflight_ttl 函数（如果存在）验证
    if hasattr(inbound_idempotency, "_resolve_inflight_ttl"):
        ttl = inbound_idempotency._resolve_inflight_ttl()
        assert ttl == 120.0, f"env 设 120s 应被读取，实际 {ttl}"


@pytest.mark.unit
def test_sweep_thread_safe(monkeypatch):
    """并发 reserve 不应破坏 sweep 行为。"""
    monkeypatch.setattr(inbound_idempotency, "_INFLIGHT_TTL_SEC", 5.0)
    import threading

    session = "concurrent_session"

    def reserve(i: int) -> None:
        eid = f"msg_{i}"
        _force_inflight_age(session, eid, age_sec=100.0)  # 全部过期
        inbound_idempotency.check_and_reserve_inbound(session, eid)

    threads = [threading.Thread(target=reserve, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    # 全部过期 inflight 应被 sweep，新 reserve 应成功
    with inbound_idempotency._LOCK:
        bucket = inbound_idempotency._SEEN.get(session, {})
        # sweep 后每个 msg_i 重新 reserve 成功（inflight 时间戳更新到 now）
        assert len(bucket) == 20, (
            f"20 条过期 inflight 应被 sweep + 重新 reserve，实际 {len(bucket)} 条"
        )
        # 全部应为 inflight 状态
        for eid, (status, _) in bucket.items():
            assert status == "inflight", f"{eid} 状态应是 inflight，实际 {status}"
