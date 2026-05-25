"""Gateway inbound message queue."""

from __future__ import annotations

from butler.gateway.message_queue import (
    classify_inbound_priority,
    enqueue_inbound,
    format_queued_ack,
    pending_count,
    pop_next,
    reset_queue,
)


def test_classify_priority():
    assert classify_inbound_priority("hello") == "next"
    assert classify_inbound_priority("/紧急 停") == "now"
    assert classify_inbound_priority("/稍后 再说") == "later"


def test_enqueue_pop_order(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_MESSAGE_QUEUE", "1")
    reset_queue("s1")
    enqueue_inbound("s1", "later msg", priority="later")
    enqueue_inbound("s1", "now msg", priority="now")
    enqueue_inbound("s1", "next msg", priority="next")
    assert pending_count("s1") == 3
    first = pop_next("s1")
    assert first is not None and first.text == "now msg"
    second = pop_next("s1")
    assert second is not None and second.priority == "next"
    reset_queue()


def test_dedupe_same_text(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_MESSAGE_QUEUE", "1")
    reset_queue("s2")
    assert enqueue_inbound("s2", "same")
    assert not enqueue_inbound("s2", "same")
    reset_queue()


def test_format_ack():
    assert "队列" in format_queued_ack(pending=2)
