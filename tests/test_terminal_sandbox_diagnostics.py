"""Tests for terminal sandbox diagnostics and audit integration."""

from __future__ import annotations

import pytest

from butler.ops.security_audit import run_security_audit
from butler.ops.terminal_sandbox_diagnostics import (
    audit_terminal_sandbox_findings,
    collect_terminal_sandbox_status,
    format_terminal_sandbox_diagnostic_lines,
)


def test_collect_status_terminal_off(monkeypatch):
    monkeypatch.delenv("BUTLER_ENABLE_TERMINAL", raising=False)
    monkeypatch.delenv("BUTLER_TERMINAL_SANDBOX", raising=False)
    st = collect_terminal_sandbox_status()
    assert st.terminal_enabled is False
    assert "未启用" in st.policy_summary


def test_audit_warns_when_terminal_on_sandbox_off(monkeypatch):
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "0")
    findings = audit_terminal_sandbox_findings()
    codes = {f.code for f in findings}
    assert "TERMINAL_NO_OS_SANDBOX" in codes


def test_audit_critical_when_sandbox_fail_closed_no_bwrap(monkeypatch):
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE", "1")
    monkeypatch.setattr(
        "butler.tools.terminal_sandbox.bubblewrap_path",
        lambda: None,
    )
    findings = audit_terminal_sandbox_findings()
    assert any(f.code == "TERMINAL_SANDBOX_NO_BWRAP" and f.level == "critical" for f in findings)


def test_security_audit_includes_sandbox_findings(monkeypatch):
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "0")
    findings = run_security_audit()
    assert any(f.code == "TERMINAL_NO_OS_SANDBOX" for f in findings)


def test_format_diagnostic_lines_include_policy(monkeypatch):
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "0")
    lines = format_terminal_sandbox_diagnostic_lines()
    assert any("Terminal 隔离" in line for line in lines)
