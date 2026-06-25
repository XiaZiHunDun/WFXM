"""Integration: /详细 on WeChat attaches long report as .md export."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.gateway.commands import info_commands
from butler.report import AgentReport, cache_report, clear_report_cache


def _ctx(*, session_key: str, platform: str = "wechat", external_id: str = "owner1"):
    from butler.gateway.command_registry import CommandContext

    return CommandContext(
        cmd="/详细",
        arg="",
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=None,
        session_registry=None,
    )


@pytest.mark.unit
def test_cmd_detail_attaches_md_on_wechat_long_report(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    monkeypatch.setenv("BUTLER_WECHAT_ATTACH_DETAIL", "1")

    clear_report_cache()
    sk = "wechat:owner1:proj"
    cache_report(
        AgentReport(
            headline="开发代理已完成任务",
            summary="变更摘要\n" + ("详细行 " * 120),
            success=True,
            task_id="task_attach_smoke",
            changes=[],
        ),
        session_key=sk,
    )

    with patch("butler.gateway.owner_gate.is_gateway_owner", return_value=True):
        out = info_commands._cmd_detail(_ctx(session_key=sk))

    assert out is not None
    assert "附件" in out
    files = list((tmp_path / "exports").glob("detail_task_attach_smoke_*.md"))
    assert len(files) == 1
    assert str(files[0].resolve()) in out


@pytest.mark.unit
def test_cmd_detail_skips_attach_for_short_report(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    monkeypatch.setenv("BUTLER_WECHAT_ATTACH_DETAIL", "1")

    clear_report_cache()
    sk = "wechat:owner1:proj"
    cache_report(
        AgentReport(
            headline="ok",
            summary="短报告",
            success=True,
            task_id="task_short",
            changes=[],
        ),
        session_key=sk,
    )

    with patch("butler.gateway.owner_gate.is_gateway_owner", return_value=True):
        out = info_commands._cmd_detail(_ctx(session_key=sk))

    assert out is not None
    assert "附件" not in out
    assert not (tmp_path / "exports").exists() or not list((tmp_path / "exports").glob("*.md"))


@pytest.mark.unit
def test_cmd_detail_non_wechat_no_path_line(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")

    clear_report_cache()
    sk = "cli:owner1:proj"
    cache_report(
        AgentReport(
            headline="ok",
            summary="x" * 600,
            success=True,
            task_id="task_cli",
            changes=[],
        ),
        session_key=sk,
    )

    with patch("butler.gateway.owner_gate.is_gateway_owner", return_value=True):
        out = info_commands._cmd_detail(_ctx(session_key=sk, platform="cli"))

    assert out is not None
    assert str(tmp_path / "exports") not in out
