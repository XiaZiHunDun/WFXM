"""Gateway OpenClaw features: reply admission, bot loop guard, terminal approval."""

from __future__ import annotations

import pytest

from butler.gateway.bot_loop_guard import (
    bot_loop_guard_enabled,
    record_and_should_suppress,
)
from butler.gateway.reply_admission import (
    clear_session,
    release,
    try_admit,
)
from butler.tools.terminal_approval import (
    argv_fingerprint,
    check_approval,
    parse_approve_command,
    store_approval,
)


def test_reply_admission_single_flight(monkeypatch):
    monkeypatch.setenv("BUTLER_REPLY_ADMISSION", "1")
    clear_session("sess-a")
    t1 = try_admit("sess-a")
    assert t1 is not None
    t2 = try_admit("sess-a")
    assert t2 is None
    release(t1)
    t3 = try_admit("sess-a")
    assert t3 is not None
    release(t3)
    clear_session("sess-a")


def test_bot_loop_guard_disabled_by_default(monkeypatch):
    monkeypatch.setenv("BUTLER_BOT_LOOP_GUARD", "0")
    assert not bot_loop_guard_enabled()
    suppress, _ = record_and_should_suppress(
        chat_id="g1",
        sender_id="bot@test",
        text="@otherbot hi",
    )
    assert not suppress


def test_bot_loop_guard_suppresses_after_threshold(monkeypatch):
    monkeypatch.setenv("BUTLER_BOT_LOOP_GUARD", "1")
    monkeypatch.setenv("BUTLER_BOT_LOOP_PAIR_THRESHOLD", "3")
    chat, sender = "room1", "mybot@openim"
    for _ in range(4):
        record_and_should_suppress(chat_id=chat, sender_id=sender, text="@peer hi")
    suppress, reason = record_and_should_suppress(
        chat_id=chat,
        sender_id=sender,
        text="@peer again",
    )
    assert suppress
    assert "bot_loop" in reason


def test_terminal_approval_binding(tmp_butler_home, monkeypatch):
    monkeypatch.setenv("BUTLER_TERMINAL_REQUIRE_APPROVAL", "1")
    cmd = "echo hello"
    fp = store_approval(cmd, cwd="/tmp")
    assert len(fp) == 32
    assert check_approval(cmd, cwd="/tmp") is None
    assert check_approval("echo other", cwd="/tmp") is not None


def test_parse_approve_command():
    assert parse_approve_command("/批准执行 ls -la") == "ls -la"
    assert parse_approve_command("/approve-exec pwd") == "pwd"
    assert parse_approve_command("/help") is None


def test_tool_loop_ping_pong(monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_LOOP_DETECTORS", "ping_pong")
    from butler.core.tool_loop_detect import get_tool_loop_detector

    det = get_tool_loop_detector()
    det.reset_for_turn()
    for i in range(8):
        name = "tool_a" if i % 2 == 0 else "tool_b"
        det.record_call(name, f"hash{i % 2}", "{}")
    dec = det.check_before_call("tool_a", {"x": 1})
    assert dec is not None
    assert dec.detector == "ping_pong"
