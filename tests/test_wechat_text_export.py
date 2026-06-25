"""Tests for WeChat md/txt export attachment."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.gateway.wechat_text_export import (
    attach_delegate_enabled,
    build_delegate_completion_message,
    maybe_attach_wechat_file,
    write_text_export,
)
from butler.report import AgentReport


@pytest.mark.unit
def test_write_text_export_under_butler_home(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    path = write_text_export("# title\n\nbody", name_prefix="test_report")
    assert path is not None
    assert path.parent == tmp_path / "exports"
    assert path.suffix == ".txt"
    assert "body" in path.read_text(encoding="utf-8")


@pytest.mark.unit
def test_maybe_attach_skips_short_text(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    out = maybe_attach_wechat_file(
        "brief",
        "short",
        platform="wechat",
        name_prefix="x",
        min_chars=100,
    )
    assert out == "brief"
    assert not list((tmp_path / "exports").glob("*"))


@pytest.mark.unit
def test_maybe_attach_caps_long_chat_summary(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    full = "行内容\n" * 100
    out = maybe_attach_wechat_file(
        full,
        full,
        platform="wechat",
        name_prefix="detail_task",
    )
    assert "…" in out
    assert "附件" in out
    path_lines = [ln for ln in out.splitlines() if ln.strip().startswith("/")]
    body = "\n".join(ln for ln in out.splitlines() if ln not in path_lines)
    assert len(body) <= 360


@pytest.mark.unit
def test_maybe_attach_appends_path_line(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    full = "x" * 500
    out = maybe_attach_wechat_file(
        "summary",
        full,
        platform="wechat",
        name_prefix="detail_task",
    )
    assert "summary" in out
    assert "附件" in out
    files = list((tmp_path / "exports").glob("detail_task_*.txt"))
    assert len(files) == 1
    assert str(files[0].resolve()) in out


@pytest.mark.unit
def test_maybe_attach_non_wechat_returns_full(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    full = "y" * 800
    out = maybe_attach_wechat_file("a", full, platform="cli", name_prefix="n")
    assert out == "a"


@pytest.mark.unit
def test_wechat_attach_suffix_defaults_txt(monkeypatch):
    monkeypatch.delenv("BUTLER_WECHAT_ATTACH_SUFFIX", raising=False)
    from butler.gateway.wechat_text_export import wechat_attach_suffix

    assert wechat_attach_suffix() == ".txt"


@pytest.mark.unit
def test_wechat_attach_suffix_md_override(monkeypatch):
    monkeypatch.setenv("BUTLER_WECHAT_ATTACH_SUFFIX", "md")
    from butler.gateway.wechat_text_export import wechat_attach_suffix

    assert wechat_attach_suffix() == ".md"


@pytest.mark.unit
def test_build_delegate_completion_message_attaches(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.wechat_text_export.get_butler_home", lambda: tmp_path)
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    monkeypatch.setenv("BUTLER_WECHAT_ATTACH_DELEGATE", "1")
    report = AgentReport(
        headline="开发代理已完成任务",
        summary="done " * 200,
        success=True,
        task_id="task_deadbeef1234",
        changes=[],
    )
    out = build_delegate_completion_message(report, platform="wechat")
    assert attach_delegate_enabled()
    assert "task_deadbeef1234" in out or "delegate_" in out
    assert str(tmp_path / "exports") in out or any((tmp_path / "exports").glob("delegate_*.txt"))
