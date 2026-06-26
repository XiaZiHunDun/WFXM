"""PROD-P5: Owner UX debt acceptance tests."""

from __future__ import annotations

import time

import pytest


@pytest.mark.unit
def test_p5_01_extract_task_id_from_completion_text():
    from butler.gateway.delegate_push_dedup import extract_task_id_from_text

    body = "内容代理已完成任务\n任务 task_a2b748f6d218 · 迭代 3 轮"
    assert extract_task_id_from_text(body) == "task_a2b748f6d218"


@pytest.mark.unit
def test_p5_01_dedup_blocks_second_push(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_PUSH_DEDUP", "1")
    from butler.gateway import delegate_push_dedup as mod

    mod._PUSHED.clear()
    chat = "wx:dedup-test"
    tid = "task_dedup001"
    ok1, _ = mod.should_deliver_delegate_push(chat, tid)
    assert ok1 is True
    mod.mark_delegate_push_delivered(chat, tid)
    ok2, reason = mod.should_deliver_delegate_push(chat, tid)
    assert ok2 is False
    assert "dedup" in reason


@pytest.mark.unit
def test_p5_01_stale_push_suppressed(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_PUSH_DEDUP", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_PUSH_MAX_AGE_SECONDS", "60")
    from butler.gateway import delegate_push_dedup as mod

    mod._PUSHED.clear()
    monkeypatch.setattr(
        mod,
        "_task_completed_epoch",
        lambda _tid: time.time() - 120,
    )
    ok, reason = mod.should_deliver_delegate_push("wx:stale", "task_stale001")
    assert ok is False
    assert reason.startswith("stale:")


@pytest.mark.unit
def test_p5_01_defers_push_during_inbound(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DEFER_DELEGATE_PUSH_DURING_INBOUND", "1")
    from butler.gateway.delegate_push_dedup import (
        flush_deferred_delegate_pushes,
        gateway_inbound_guard,
        is_inbound_active,
        maybe_defer_delegate_push,
    )

    chat = "wx:inbound"
    assert maybe_defer_delegate_push(chat, "任务 task_x", kind="delegate") is False
    with gateway_inbound_guard(chat):
        assert is_inbound_active(chat)
        assert maybe_defer_delegate_push(chat, "任务 task_x", kind="delegate") is True
    assert not is_inbound_active(chat)
    assert flush_deferred_delegate_pushes(chat) == []


@pytest.mark.unit
@pytest.mark.skip(reason="PROD-P5-02 backlog: ingest phrase pre-dispatch")
def test_p5_02_ingest_phrase_expands_without_remember_prompt():
    raise NotImplementedError


@pytest.mark.unit
@pytest.mark.skip(reason="PROD-P5-03 backlog: ingest skips DEV_VERIFY_GATE")
def test_p5_03_ingest_delegate_success_without_verify_gate():
    raise NotImplementedError
