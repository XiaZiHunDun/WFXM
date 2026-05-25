"""WeChat outbound file delivery for session export."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.gateway.outbound_files import (
    append_wechat_file_delivery_line,
    extract_deliverable_local_files,
    is_deliverable_export_file,
)


@pytest.mark.unit
def test_deliverable_under_butler_exports(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    exp = tmp_path / "exports"
    exp.mkdir(parents=True)
    md = exp / "wx_test_2026.md"
    md.write_text("# hi\n", encoding="utf-8")
    assert is_deliverable_export_file(md)
    assert not is_deliverable_export_file(tmp_path / "exports" / "missing.md")


@pytest.mark.unit
def test_deliverable_project_exports(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    ws = tmp_path / "proj"
    out = ws / ".butler" / "exports"
    out.mkdir(parents=True)
    md = out / "session.md"
    md.write_text("x", encoding="utf-8")
    assert is_deliverable_export_file(md)


@pytest.mark.unit
def test_extract_and_append(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    monkeypatch.setenv("BUTLER_EXPORT_SEND_WECHAT_FILE", "1")
    exp = tmp_path / "exports"
    exp.mkdir(parents=True)
    md = exp / "a.md"
    md.write_text("body", encoding="utf-8")
    p = str(md.resolve())

    files, cleaned = extract_deliverable_local_files(f"摘要\n\n{p}")
    assert files == [p]
    assert "摘要" in cleaned
    assert p not in cleaned

    out = append_wechat_file_delivery_line("已导出", md)
    assert p in out
    assert out.endswith(p) or f"\n\n{p}" in out


@pytest.mark.unit
def test_rejects_outside_exports(tmp_path, monkeypatch):
    monkeypatch.setattr("butler.gateway.outbound_files.get_butler_home", lambda: tmp_path)
    evil = tmp_path / "evil.md"
    evil.write_text("x", encoding="utf-8")
    assert not is_deliverable_export_file(evil)
