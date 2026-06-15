"""Morning brief push (opt-in)."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from butler.ops.morning_brief_push import (
    build_morning_brief_text,
    morning_brief_enabled,
    push_morning_brief,
)


def test_morning_brief_disabled_by_default(monkeypatch):
    monkeypatch.delenv("BUTLER_MORNING_BRIEF", raising=False)
    assert morning_brief_enabled() is False
    assert push_morning_brief()["ok"] is False


def test_push_morning_brief_when_enabled(monkeypatch):
    monkeypatch.setenv("BUTLER_MORNING_BRIEF", "1")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner-chat")
    monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "灵文1号")

    with patch(
        "butler.ops.morning_brief_push.build_morning_brief_text",
        return_value="📬 管家简报\n\n收件箱：暂无",
    ), patch(
        "butler.runtime.notify.push_runtime_message",
        return_value=True,
    ) as push:
        out = push_morning_brief()
    assert out["ok"] is True
    push.assert_called_once()


def test_build_morning_brief_text(monkeypatch):
    monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "灵文1号")
    with patch("butler.ops.butler_inbox.format_owner_brief", return_value="brief-line"):
        text = build_morning_brief_text(session_key="wechat:u1:灵文1号")
    assert text == "brief-line"
