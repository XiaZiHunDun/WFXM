"""Sprint 24 P1-3.2: is_approved diagnostics 透传 + revoke + /诊断集成 + workflow 不可穿透."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.permissions.approvals import (
    ApprovalRequest,
    grant_always,
    grant_once,
    is_approved,
    save_pending,
)


class TestIsApprovedDiagnostics:
    def test_diagnostics_none_safe_when_no_hit(self, tmp_path, monkeypatch):
        """无命中时 diagnostics 不会被写入任何键."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        diag: dict = {}
        assert is_approved("s_no_hit", req, diagnostics=diag) is False
        assert diag == {}

    def test_diagnostics_records_always_hit(self, tmp_path, monkeypatch):
        """always 命中时写入 approval_cache_hit + source=always."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        grant_always("s_always", permission="p", tool="t", pattern="pat")
        diag: dict = {}
        assert is_approved("s_always", req, diagnostics=diag) is True
        assert diag.get("approval_cache_hit") is True
        assert diag.get("approval_cache_source") == "always"

    def test_diagnostics_records_once_hit(self, tmp_path, monkeypatch):
        """once 命中时写入 source=once."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        save_pending("s_once", req)
        grant_once("s_once")
        diag: dict = {}
        assert is_approved("s_once", req, diagnostics=diag) is True
        assert diag.get("approval_cache_source") == "once"

    def test_diagnostics_omitted_kw_only_backward_compatible(self, tmp_path, monkeypatch):
        """不传 diagnostics 时仍正常工作 (向后兼容)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        req = ApprovalRequest(permission="p", tool="t", pattern="pat")
        grant_always("s_bwcompat", permission="p", tool="t", pattern="pat")
        assert is_approved("s_bwcompat", req) is True  # 不传 diagnostics
