"""Tests for butler.skills.learn and CLI ``butler skills learn``."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.skills.learn import parse_learn_response, run_skill_learn


@pytest.mark.unit
def test_parse_learn_response_strips_fence():
    raw = """```json
{"name": "demo", "description": "d", "triggers": ["t"], "content": "body"}
```"""
    data = parse_learn_response(raw)
    assert data["name"] == "demo"
    assert data["triggers"] == ["t"]


@pytest.mark.unit
def test_parse_learn_response_missing_name():
    with pytest.raises(ValueError, match="name"):
        parse_learn_response('{"description": "x"}')


@pytest.mark.unit
def test_run_skill_learn_short_description():
    out = run_skill_learn("短", MagicMock())
    assert out["ok"] is False
    assert "8" in out["error"]


@pytest.mark.unit
def test_run_skill_learn_pending(monkeypatch):
    sm = MagicMock()
    sm.create.return_value = "pending"
    payload = {
        "name": "lint-helper",
        "description": "lint code",
        "triggers": ["lint"],
        "content": "---\nname: lint-helper\n---\nbody",
    }
    with patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value=json.dumps(payload),
    ):
        out = run_skill_learn("帮助我在提交前跑 lint 检查", sm)
    assert out["ok"] is True
    assert out["outcome"] == "pending"
    assert "lint-helper" in out["message"]
    sm.create.assert_called_once_with(
        "lint-helper",
        "lint code",
        ["lint"],
        payload["content"],
    )


@pytest.mark.unit
def test_run_skill_learn_invalid_json():
    sm = MagicMock()
    with patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value="not json",
    ):
        out = run_skill_learn("描述足够长的技能学习请求", sm)
    assert out["ok"] is False
    assert "JSON" in out["error"]
    sm.create.assert_not_called()


@pytest.mark.unit
def test_cli_skills_learn(monkeypatch, capsys):
    monkeypatch.setenv("BUTLER_HOME", "/tmp/butler-test-home")
    sm = MagicMock()
    sm.create.return_value = "created"
    payload = {
        "name": "cli-skill",
        "description": "from cli",
        "triggers": ["cli"],
        "content": "body",
    }
    with patch(
        "butler.cli.skills_registry._skill_manager_for_cli",
        return_value=sm,
    ), patch(
        "butler.transport.auxiliary_client.auxiliary_complete",
        return_value=json.dumps(payload),
    ):
        from butler.cli.skills_registry import _cmd_learn
        import argparse

        ns = argparse.Namespace(description="通过 CLI 学习一条新技能", project="")
        rc = _cmd_learn(ns)
    assert rc == 0
    captured = capsys.readouterr()
    assert "cli-skill" in captured.out
