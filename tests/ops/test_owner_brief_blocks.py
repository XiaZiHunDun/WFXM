"""Tests for /简报 four-block layout (PROD-P1-02)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.handler_helpers import _WELCOME_TEXT
from butler.ops.butler_inbox import format_owner_brief
from butler.ops.owner_brief_blocks import format_overnight_jobs_lines


@pytest.mark.unit
def test_welcome_text_three_step_onboarding():
    assert "三步上手" in _WELCOME_TEXT
    assert "/切换" in _WELCOME_TEXT
    assert "只读" in _WELCOME_TEXT
    assert "委派" in _WELCOME_TEXT


@pytest.mark.unit
def test_format_owner_brief_four_blocks(monkeypatch):
    monkeypatch.setattr("butler.tools.project_todos._load", lambda _ws: [])
    monkeypatch.setattr("butler.tools.reminder._load_all", lambda: [])
    monkeypatch.setattr(
        "butler.ops.owner_brief_blocks.format_overnight_jobs_lines",
        lambda _name: ["  昨夜无执行记录"],
    )

    orch = MagicMock()
    orch._settings.default_provider = "minimax"
    orch.project_manager.get_current.return_value = type(
        "P", (), {"name": "普通试点项目", "workspace": "/tmp/ws"}
    )()
    orch._reload_project_memory = MagicMock()
    orch._project_memory = None

    text = format_owner_brief(orch, "wechat:u:demo")
    assert "【待办】" in text
    assert "【队列】" in text
    assert "【门控】" in text
    assert "【昨夜 job】" in text
    assert text.index("【待办】") < text.index("【队列】") < text.index("【门控】")
    assert "更多：/inbox" in text


@pytest.mark.unit
def test_format_overnight_jobs_recent_run():
    now = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
    rows = [
        {
            "id": "factory-daily",
            "enabled": True,
            "last_at": now,
            "last_success": True,
        }
    ]
    with patch("butler.runtime.service.runtime_enabled", return_value=True), patch(
        "butler.runtime.service.list_jobs_status", return_value=rows
    ):
        lines = format_overnight_jobs_lines("灵文1号")
    assert any("factory-daily" in ln for ln in lines)
    assert any("✓" in ln for ln in lines)
