"""Transcript epoch helpers — turn tool boundary."""

from __future__ import annotations

import pytest

from butler.core.session_epoch import load_current_turn_tool_actions


@pytest.mark.unit
def test_load_current_turn_tool_actions_skips_skill_injected_user(monkeypatch):
    rows = [
        {"type": "user", "content": "请委派开发代理读 README\n\n## 相关知识（Butler Skill）"},
        {"type": "tool_action", "tool": "delegate_task"},
        {"type": "user", "content": "## 相关知识（Butler Skill）\n> 指针加载"},
        {"type": "tool_action", "tool": "slash:/切换"},
    ]

    monkeypatch.setattr(
        "butler.core.session_epoch.load_epoch_transcript_rows",
        lambda _sk, max_lines=500: rows,
    )
    tools = load_current_turn_tool_actions("sk")
    assert [t.get("tool") for t in tools] == ["delegate_task", "slash:/切换"]


@pytest.mark.unit
def test_load_current_turn_tool_actions_continues_past_skill_user(monkeypatch):
    rows = [
        {"type": "user", "content": "请委派开发代理"},
        {"type": "tool_action", "tool": "delegate_task"},
        {"type": "user", "content": "## 相关知识（Butler Skill）\n> 指针"},
        {"type": "tool_action", "tool": "read_file"},
    ]

    monkeypatch.setattr(
        "butler.core.session_epoch.load_epoch_transcript_rows",
        lambda _sk, max_lines=500: rows,
    )
    tools = load_current_turn_tool_actions("sk")
    assert [t.get("tool") for t in tools] == ["delegate_task", "read_file"]


@pytest.mark.unit
def test_load_tool_actions_since_strict_after_cutoff(monkeypatch):
    from butler.core.session_epoch import load_tool_actions_since

    rows = [
        {"type": "tool_action", "tool": "old", "ts": "2026-06-22T10:00:00+00:00"},
        {"type": "tool_action", "tool": "new", "ts": "2026-06-22T10:00:01+00:00"},
    ]
    monkeypatch.setattr(
        "butler.core.session_epoch.load_epoch_transcript_rows",
        lambda _sk, max_lines=500: rows,
    )
    out = load_tool_actions_since("sk", "2026-06-22T10:00:00+00:00")
    assert [t.get("tool") for t in out] == ["new"]
