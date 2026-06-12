"""Tests for run_pytest dev_engine tool."""

from __future__ import annotations

from butler.dev_engine.dev_tools import tool_run_pytest


def test_run_pytest_pass(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    (tmp_path / "ok.py").write_text("def ok():\n    return 1\n", encoding="utf-8")
    (tmp_path / "test_b9.py").write_text(
        "from ok import ok\n\ndef test_ok():\n    assert ok() == 1\n",
        encoding="utf-8",
    )
    out = tool_run_pytest("test_b9.py", session_key="_test")
    assert out.get("passed") is True
    assert out.get("exit_code") == 0


def test_run_pytest_fail_with_hint(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    (tmp_path / "svc.py").write_text("def ping():\n    return 'nope'\n", encoding="utf-8")
    (tmp_path / "test_b9.py").write_text(
        "from svc import ping\n\ndef test_ping():\n    assert ping() == 'pong'\n",
        encoding="utf-8",
    )
    out = tool_run_pytest("test_b9.py", session_key="_test")
    assert out.get("passed") is False
    assert out.get("hint")
