"""butler doctor static security audit."""

from __future__ import annotations

import os

from butler.ops.security_audit import format_audit_report, run_security_audit


def test_audit_critical_without_owner(monkeypatch):
    monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
    monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
    findings = run_security_audit()
    codes = {f.code for f in findings}
    assert "NO_GATEWAY_OWNER" in codes
    report = format_audit_report(findings)
    assert "CRITICAL" in report or "critical" in report.lower()


def test_audit_terminal_warn(monkeypatch):
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
    findings = run_security_audit()
    assert any(f.code == "TERMINAL_ENABLED" for f in findings)


def test_audit_mcp_hosts_warn(monkeypatch):
    monkeypatch.setenv("BUTLER_MCP_ENABLED", "1")
    monkeypatch.delenv("BUTLER_MCP_HTTP_HOSTS_ALLOW", raising=False)
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "x")
    findings = run_security_audit()
    assert any(f.code == "MCP_HTTP_HOSTS_OPEN" for f in findings)
