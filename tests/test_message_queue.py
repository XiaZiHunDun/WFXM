"""Gateway inbound message queue and queue settings."""

from __future__ import annotations

import pytest

from butler.gateway import queue_settings as qs
from butler.gateway.message_queue import (
    classify_inbound_priority,
    enqueue_inbound,
    format_queued_ack,
    pending_count,
    pop_all_merged,
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


def test_queue_cap_drop_old(monkeypatch, tmp_butler_home):
    monkeypatch.setenv("BUTLER_GATEWAY_MESSAGE_QUEUE", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_CAP", "2")
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_DROP", "old")
    qs.clear_session_override("cap-old")
    reset_queue("cap-old")
    enqueue_inbound("cap-old", "first")
    enqueue_inbound("cap-old", "second")
    enqueue_inbound("cap-old", "third")
    assert pending_count("cap-old") == 2
    first = pop_next("cap-old")
    assert first is not None and first.text == "second"
    reset_queue("cap-old")


def test_queue_cap_drop_new_rejects(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_MESSAGE_QUEUE", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_CAP", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_QUEUE_DROP", "new")
    reset_queue("cap-new")
    enqueue_inbound("cap-new", "first")
    assert not enqueue_inbound("cap-new", "second")
    assert pending_count("cap-new") == 1
    reset_queue("cap-new")


def test_pop_all_merged_collect(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_MESSAGE_QUEUE", "1")
    reset_queue("coll")
    enqueue_inbound("coll", "消息一", priority="next")
    enqueue_inbound("coll", "消息二", priority="now")
    merged = pop_all_merged("coll")
    assert merged is not None
    assert "消息一" in merged.text and "消息二" in merged.text
    assert pending_count("coll") == 0
    reset_queue("coll")


def test_parse_queue_command():
    mode, opts, err = qs.parse_queue_command("collect cap:5 drop:summarize debounce:1s")
    assert err is None
    assert mode == "collect"
    assert opts["cap"] == 5
    assert opts["drop"] == "summarize"
    assert opts["debounce_ms"] == 1000


def test_apply_queue_command_session_override(tmp_butler_home):
    qs.clear_session_override("sess-q")
    text = qs.apply_queue_command("sess-q", "interrupt cap:10")
    assert "interrupt" in text
    assert qs.get_queue_mode("sess-q") == "interrupt"
    assert qs.session_queue_cap("sess-q") == 10
    qs.clear_session_override("sess-q")
    assert qs.get_queue_mode("sess-q") == qs.default_queue_mode()
