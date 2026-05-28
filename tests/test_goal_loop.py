"""Tests for goal loop state."""

from __future__ import annotations

from butler.core.goal_loop import (
    is_goal_loop_active,
    next_goal_message,
    start_goal_loop,
    stop_goal_loop,
)


def test_goal_loop_start_stop(tmp_path, monkeypatch):
    root = tmp_path / "sessions"
    monkeypatch.setattr(
        "butler.core.goal_loop._state_path",
        lambda sk: root / sk.replace(":", "_") / "goal_loop.json",
    )
    sk = "cli:default"
    assert start_goal_loop(sk, "build feature X").startswith("已启动")
    assert is_goal_loop_active(sk)
    msg = next_goal_message(sk)
    assert msg is not None
    assert "build feature X" in msg
    assert stop_goal_loop(sk).startswith("已停止")
    assert not is_goal_loop_active(sk)
