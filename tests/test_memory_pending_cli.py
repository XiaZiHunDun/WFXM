"""Tests for ``butler memory pending|approve|reject`` CLI."""

from __future__ import annotations

import argparse
from unittest.mock import MagicMock, patch

import pytest

from butler.memory.owner_write_pending import list_owner_pending, queue_owner_write
from butler.memory.pending_cli import (
    approve_pending_text,
    list_pending_text,
    reject_pending_text,
)


@pytest.mark.unit
def test_list_pending_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    text = list_pending_text()
    assert "没有" in text or "为空" in text


@pytest.mark.unit
def test_list_pending_owner_item(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    queue_owner_write(scope="owner_profile", content="prefers bullet summaries")
    text = list_pending_text()
    assert "所有者记忆待审" in text
    assert "owner_profile" in text


@pytest.mark.unit
def test_approve_owner_pending_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    queue_owner_write(scope="owner_profile", content="cli approve me")

    class FakeProfile:
        def add(self, content):
            self.last = content
            return {"success": True}

        def sync(self):
            pass

    class FakeBM:
        def __init__(self):
            self.profile = FakeProfile()

        def sync_profile_vectors(self):
            pass

    with patch(
        "butler.memory.pending_cli.build_memory_orchestrator_stub",
    ) as build:
        orch = MagicMock()
        orch.butler_memory = FakeBM()
        orch._project_memory = None
        orch.project_manager = MagicMock(get_current=MagicMock(return_value=None))
        orch._reload_project_memory = MagicMock()
        build.return_value = orch
        out = approve_pending_text("1")
    assert "批准" in out
    assert len(list_owner_pending()) == 0


@pytest.mark.unit
def test_reject_owner_pending_cli(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    queue_owner_write(scope="owner_experience", content="reject via cli")
    with patch("butler.memory.pending_cli.build_memory_orchestrator_stub") as build:
        orch = MagicMock()
        orch.butler_memory = MagicMock()
        orch._project_memory = None
        orch.project_manager = MagicMock(get_current=MagicMock(return_value=None))
        orch._reload_project_memory = MagicMock()
        build.return_value = orch
        out = reject_pending_text("1")
    assert "拒绝" in out
    assert list_owner_pending() == []


@pytest.mark.unit
def test_cli_memory_pending_command(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    queue_owner_write(scope="owner_profile", content="from cli command")
    with patch(
        "butler.memory.pending_cli.list_pending_text",
        return_value="所有者记忆待审: 1 条",
    ):
        from butler.cli.memory_cli import _cmd_memory_pending

        rc = _cmd_memory_pending(argparse.Namespace(project="", tenant="default"))
    assert rc == 0
    assert "待审" in capsys.readouterr().out
