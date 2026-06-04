"""Sprint 24 P1-3.2: is_approved diagnostics 透传 + revoke + /诊断集成 + workflow 不可穿透."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.permissions.approvals import (
    ApprovalRequest,
    clear_always,
    grant_always,
    grant_once,
    is_approved,
    revoke_always,
    save_pending,
    summarize_approvals,
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


class TestRevokeAlways:
    def test_revoke_specific_entry(self, tmp_path, monkeypatch):
        """revoke_always 按 permission+tool+pattern 匹配删除."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s_revoke_1", permission="write_file", tool="*", pattern="*.env")
        grant_always("s_revoke_1", permission="read_file", tool="*", pattern="*")
        msg = revoke_always("s_revoke_1", permission="write_file")
        assert "已撤销" in msg
        from butler.permissions.approvals import list_always
        remaining = list_always("s_revoke_1")
        assert len(remaining) == 1
        assert remaining[0]["permission"] == "read_file"

    def test_revoke_no_match_returns_status(self, tmp_path, monkeypatch):
        """无匹配时返 '未找到匹配项' 提示."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s_revoke_2", permission="write_file", tool="*", pattern="*")
        msg = revoke_always("s_revoke_2", permission="nonexistent")
        assert "未找到" in msg
        from butler.permissions.approvals import list_always
        assert len(list_always("s_revoke_2")) == 1  # 原项保留

    def test_revoke_all_filters_empty_returns_error(self, tmp_path, monkeypatch):
        """全空过滤返错误 (防止误删全部)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s_revoke_3", permission="p1")
        msg = revoke_always("s_revoke_3")
        assert "请指定" in msg or "至少一项" in msg
        from butler.permissions.approvals import list_always
        assert len(list_always("s_revoke_3")) == 1  # 原项保留

    def test_clear_always_removes_all(self, tmp_path, monkeypatch):
        """clear_always 清空所有 always 记录."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s_clear_1", permission="p1")
        grant_always("s_clear_1", permission="p2")
        msg = clear_always("s_clear_1")
        assert "已清除 2 项" in msg
        from butler.permissions.approvals import list_always
        assert list_always("s_clear_1") == []

    def test_clear_always_no_entries_is_ok(self, tmp_path, monkeypatch):
        """clear_always 无记录时返 '已清除 0 项' 不报错."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        msg = clear_always("s_clear_2")
        assert "已清除 0 项" in msg


class TestSummarizeApprovals:
    def test_summarize_empty_session(self, tmp_path, monkeypatch):
        """空 session 返 0/0/False."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        s = summarize_approvals("s_sum_1")
        assert s["always_count"] == 0
        assert s["once_active_count"] == 0
        assert s["has_pending"] is False

    def test_summarize_with_entries(self, tmp_path, monkeypatch):
        """含 always + once + pending 时正确统计."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        grant_always("s_sum_2", permission="p1")
        grant_always("s_sum_2", permission="p2")
        req = ApprovalRequest(permission="p3", tool="t", pattern="pat")
        save_pending("s_sum_2", req)
        grant_once("s_sum_2")
        s = summarize_approvals("s_sum_2")
        assert s["always_count"] == 2
        assert s["once_active_count"] == 1
        assert s["has_pending"] is False  # grant_once 清空 pending


class TestApprovalHealthIntegration:
    def test_health_report_includes_approval_summary(self, tmp_path, monkeypatch):
        """/诊断 应包含 approval 行 (always count / once active)."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.ops.health_report import collect_approval_stats_for_health
        grant_always("s_health_1", permission="p1")
        stats = collect_approval_stats_for_health("s_health_1")
        assert stats["always_count"] == 1
        assert stats["once_active_count"] == 0
        assert stats["has_pending"] is False

    def test_health_report_handles_empty_session(self, tmp_path, monkeypatch):
        """空 session 时 /诊断 approval stats 返 0/0/False 不抛异常."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.ops.health_report import collect_approval_stats_for_health
        stats = collect_approval_stats_for_health("s_health_empty")
        assert stats["always_count"] == 0
        assert stats["once_active_count"] == 0
        assert stats["has_pending"] is False

    def test_health_report_includes_approval_in_shared_lines(self, tmp_path, monkeypatch):
        """_shared_diagnostic_lines 应包含 '权限批准缓存' 标题行 + always count + once count."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.ops.health_report import HealthReportInput, _shared_diagnostic_lines
        from unittest.mock import MagicMock
        grant_always("s_health_2", permission="p1")
        grant_always("s_health_2", permission="p2")
        orch = MagicMock()
        orch.project_manager.get_current.return_value = None
        orch._settings = MagicMock()
        inp = HealthReportInput(
            session_key="s_health_2",
            health={},
            tool_summary={},
            mem_stats={},
            orchestrator=orch,
        )
        lines = _shared_diagnostic_lines(inp, use_mem_stats_project_name=False)
        text = "\n".join(lines)
        assert "权限批准缓存" in text
        assert "始终允许 2 项" in text
        assert "本次允许 0 项" in text


class TestRegistryCommands:
    def test_revoke_always_command_dispatch(self):
        """/撤销批准 命令已注册到 registry."""
        from butler.gateway.command_registry import lookup
        cmd = lookup("/撤销批准")
        assert cmd is not None
        assert cmd.handler is not None
        assert cmd.category == "权限安全"

    def test_clear_always_command_dispatch(self):
        """/清除始终允许 命令已注册到 registry."""
        from butler.gateway.command_registry import lookup
        cmd = lookup("/清除始终允许")
        assert cmd is not None
        assert cmd.handler is not None
        assert cmd.category == "权限安全"

    def test_revoke_always_handler_calls_revoke(self, tmp_path, monkeypatch):
        """handler 解析 arg 调 revoke_always."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        from butler.gateway.command_registry import CommandContext
        from butler.gateway.commands.permission_commands import _cmd_revoke_always
        from butler.permissions.approvals import grant_always, list_always
        grant_always("s_revoke_handler_1", permission="write_file", tool="*", pattern="*.env")
        ctx = CommandContext(
            cmd="/撤销批准", arg="write_file",
            session_key="s_revoke_handler_1", platform="wx",
            external_id="u1", orchestrator=None, session_registry=None,
        )
        msg = _cmd_revoke_always(ctx)
        assert "已撤销" in msg
        assert len(list_always("s_revoke_handler_1")) == 0

    def test_clear_always_handler_clears_all(self, tmp_path, monkeypatch):
        """handler 调 clear_always."""
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        from butler.gateway.command_registry import CommandContext
        from butler.gateway.commands.permission_commands import _cmd_clear_always
        from butler.permissions.approvals import grant_always, list_always
        grant_always("s_clear_handler_1", permission="p1")
        grant_always("s_clear_handler_1", permission="p2")
        ctx = CommandContext(
            cmd="/清除始终允许", arg="",
            session_key="s_clear_handler_1", platform="wx",
            external_id="u1", orchestrator=None, session_registry=None,
        )
        msg = _cmd_clear_always(ctx)
        assert "已清除 2 项" in msg
        assert list_always("s_clear_handler_1") == []


class TestWorkflowNotBypassed:
    def test_workflow_approval_uses_separate_storage(self, tmp_path, monkeypatch):
        """workflow 步骤审批与 tool approval cache 互不干扰.

        human_gate.is_step_approved 走 _approved_set (set in memory),
        approvals.is_approved 走 approvals.json — 两套独立.
        """
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.human_gate import is_step_approved, mark_step_approved
        from butler.permissions.approvals import (
            ApprovalRequest, grant_always, is_approved,
        )

        # 工具批准 (写文件)
        req = ApprovalRequest(permission="write_file", tool="write_file", pattern="*")
        grant_always("s_wf_iso_1", permission="write_file", tool="*", pattern="*")
        assert is_approved("s_wf_iso_1", req) is True
        # 工具批准不影响 workflow 步骤
        assert is_step_approved("s_wf_iso_1", "wf1", "step1") is False
        # workflow 标记也不影响工具
        mark_step_approved("s_wf_iso_1", "wf1", "step1")
        assert is_step_approved("s_wf_iso_1", "wf1", "step1") is True
        assert is_approved("s_wf_iso_1", req) is True  # 工具仍命中
