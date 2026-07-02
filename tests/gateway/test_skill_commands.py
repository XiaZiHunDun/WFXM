"""Gateway skill pending / learn command handlers."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.commands.skill_commands import (
    format_skill_pending_list,
    handle_skill_pending_command,
)


@pytest.mark.unit
def test_format_skill_pending_empty():
    orch = MagicMock()
    assert "没有" in format_skill_pending_list(orch)


@pytest.mark.unit
def test_skill_pending_list_with_items(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings
    from butler.skills.write_approval import queue_skill_pending

    reload_butler_settings()
    queue_skill_pending(
        name="demo-skill",
        description="demo",
        triggers=["demo"],
        content="---\nname: demo\n---\nbody",
    )
    orch = MagicMock()
    text = format_skill_pending_list(orch)
    assert "demo-skill" in text
    assert "技能待审" in text


@pytest.mark.unit
def test_approve_skill_requires_owner(monkeypatch):
    orch = MagicMock()
    monkeypatch.setattr(
        "butler.gateway.commands.skill_commands.is_gateway_owner",
        lambda **_: False,
    )
    out = handle_skill_pending_command(
        orch, "/批准技能", "1", platform="wechat", external_id="x",
    )
    assert out is not None
    assert "Owner" in out or "owner" in out.lower()


@pytest.mark.unit
def test_reject_skill_pending(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings
    from butler.skills.write_approval import list_skill_pending, queue_skill_pending

    reload_butler_settings()
    queue_skill_pending(
        name="x",
        description="d",
        triggers=[],
        content="body",
    )
    assert len(list_skill_pending()) == 1
    orch = MagicMock()
    out = handle_skill_pending_command(orch, "/拒绝技能", "1")
    assert out is not None
    assert "拒绝" in out
    assert list_skill_pending() == []


@pytest.mark.unit
def test_skill_learn_short_arg(monkeypatch):
    orch = MagicMock()
    monkeypatch.setattr(
        "butler.gateway.commands.skill_commands.is_gateway_owner",
        lambda **_: True,
    )
    from butler.gateway.commands.skill_commands import handle_skill_learn

    out = handle_skill_learn(orch, "短", platform="wechat")
    assert "用法" in out or "8" in out


@pytest.mark.unit
def test_skill_learn_queues_pending(monkeypatch):
    orch = MagicMock()
    sm = MagicMock()
    sm.create.return_value = "pending"
    orch._skill_manager = sm
    monkeypatch.setattr(
        "butler.gateway.commands.skill_commands.is_gateway_owner",
        lambda **_: True,
    )
    payload = {
        "name": "gw-skill",
        "description": "d",
        "triggers": ["t"],
        "content": "body",
    }
    with patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value=__import__("json").dumps(payload),
    ):
        from butler.gateway.commands.skill_commands import handle_skill_learn

        out = handle_skill_learn(
            orch,
            "通过微信网关学习一条足够长的技能",
            platform="wechat",
        )
    assert "gw-skill" in out
    assert "待审" in out
