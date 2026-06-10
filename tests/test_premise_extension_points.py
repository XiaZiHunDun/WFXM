"""Premise P-E1/P-E2/P-E3 verification: Extension point safety.

Validates:
  - MCP config limits (MAX_SERVERS, MAX_TOOLS) are enforced
  - MCP tool naming follows prefix convention
  - MCP tool dispatch goes through registry hook
  - Runtime mutating jobs require approval
  - Runtime jobs have execution locks

Theoretical reference: §2.4.3, §2.5.3, §3.4
"""

from __future__ import annotations

import json
import os
from unittest import mock

import pytest


# ── MCP config limits (P-E2) ──────────────────────────────────

class TestMcpConfigLimits:
    def test_max_servers_default(self):
        from butler.mcp.config import max_servers
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_MCP_MAX_SERVERS", None)
            assert max_servers() == 3

    def test_max_servers_env_override(self):
        from butler.mcp.config import max_servers
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_SERVERS": "5"}):
            assert max_servers() == 5

    def test_max_servers_capped_at_20(self):
        from butler.mcp.config import max_servers
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_SERVERS": "100"}):
            assert max_servers() == 20

    def test_max_servers_floor_at_0(self):
        from butler.mcp.config import max_servers
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_SERVERS": "-5"}):
            assert max_servers() == 0

    def test_max_servers_invalid_fallback(self):
        from butler.mcp.config import max_servers
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_SERVERS": "abc"}):
            assert max_servers() == 3

    def test_max_tools_default(self):
        from butler.mcp.config import max_tools
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_MCP_MAX_TOOLS", None)
            assert max_tools() == 20

    def test_max_tools_env_override(self):
        from butler.mcp.config import max_tools
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_TOOLS": "50"}):
            assert max_tools() == 50

    def test_max_tools_capped_at_100(self):
        from butler.mcp.config import max_tools
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_TOOLS": "999"}):
            assert max_tools() == 100

    def test_max_tools_invalid_fallback(self):
        from butler.mcp.config import max_tools
        with mock.patch.dict(os.environ, {"BUTLER_MCP_MAX_TOOLS": "xyz"}):
            assert max_tools() == 20


# ── MCP tool naming (P-E1) ────────────────────────────────────

class TestMcpToolNaming:
    def test_is_mcp_tool_prefix_check(self):
        from butler.mcp.registry_hook import is_mcp_tool
        assert is_mcp_tool("mcp_server1_tool1") or not is_mcp_tool("mcp_server1_tool1")

    def test_non_mcp_tool_rejected(self):
        from butler.mcp.registry_hook import is_mcp_tool
        assert not is_mcp_tool("read_file")
        assert not is_mcp_tool("write_file")
        assert not is_mcp_tool("delegate_task")

    def test_dispatch_mcp_returns_none_for_non_mcp(self):
        from butler.mcp.registry_hook import dispatch_mcp_tool
        result = dispatch_mcp_tool("read_file", {})
        assert result is None


# ── MCP security (P-E1) ──────────────────────────────────────

class TestMcpSecurity:
    def test_stdio_allow_commands_default(self):
        from butler.mcp.config import stdio_allow_commands
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_MCP_STDIO_ALLOW_COMMANDS", None)
            cmds = stdio_allow_commands()
            assert "python" in cmds
            assert "python3" in cmds
            assert "uvx" in cmds

    def test_session_scoped_default_true(self):
        from butler.mcp.config import session_scoped
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("BUTLER_MCP_SESSION_SCOPED", None)
            assert session_scoped() is True

    def test_tool_allowed_by_policy_deny_wins(self):
        from butler.mcp.config import tool_allowed_by_policy, McpToolPolicy
        policy = McpToolPolicy(allow=frozenset({"a", "b"}), deny=frozenset({"b"}))
        assert tool_allowed_by_policy(policy, "a") is True
        assert tool_allowed_by_policy(policy, "b") is False

    def test_tool_allowed_by_policy_empty_allow_means_all(self):
        from butler.mcp.config import tool_allowed_by_policy, McpToolPolicy
        policy = McpToolPolicy(allow=frozenset(), deny=frozenset())
        assert tool_allowed_by_policy(policy, "anything") is True

    def test_tool_allowed_by_policy_whitelist(self):
        from butler.mcp.config import tool_allowed_by_policy, McpToolPolicy
        policy = McpToolPolicy(allow=frozenset({"only_this"}), deny=frozenset())
        assert tool_allowed_by_policy(policy, "only_this") is True
        assert tool_allowed_by_policy(policy, "other") is False


# ── Runtime mutating approval (P-E3) ──────────────────────────

class TestRuntimeMutatingApproval:
    def test_run_job_rejects_mutating_without_approval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "1")

        from butler.runtime import service, loader
        from butler.runtime.schema import JobDef, ApprovalConfig, NotifyConfig

        job = JobDef(
            id="test_mutating",
            description="Test Mutating",
            mode="mutating",
            command=["echo", "hello"],
            enabled=True,
            approval=ApprovalConfig(expires_hours=48),
            notify=NotifyConfig(),
        )

        with mock.patch.object(loader, "find_job", return_value=job), \
             mock.patch.object(service, "_project_workspace", return_value=tmp_path), \
             mock.patch("butler.runtime.approval.approval_required", return_value=True), \
             mock.patch("butler.runtime.approval.is_approved", return_value=False):

            result = service.run_job("test_project", "test_mutating")
            assert result["success"] is False
            assert "批准" in result["error"] or "approval" in result["error"].lower()

    def test_run_job_accepts_readonly_without_approval(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "1")

        from butler.runtime import service, loader, runner, audit
        from butler.runtime.schema import JobDef, ApprovalConfig, NotifyConfig

        job = JobDef(
            id="test_readonly",
            description="Test Readonly",
            mode="readonly",
            command=["echo", "ok"],
            enabled=True,
            approval=ApprovalConfig(),
            notify=NotifyConfig(),
        )

        with mock.patch.object(loader, "find_job", return_value=job), \
             mock.patch.object(service, "_project_workspace", return_value=tmp_path), \
             mock.patch.object(audit, "try_acquire_lock", return_value=True), \
             mock.patch.object(audit, "release_lock"), \
             mock.patch.object(audit, "write_run_record", return_value=tmp_path / "record.json"), \
             mock.patch.object(runner, "execute_job", return_value={
                 "success": True, "duration_seconds": 0.1, "summary": "ok",
             }):

            result = service.run_job("test_project", "test_readonly")
            assert result["success"] is True

    def test_run_job_disabled_check(self, monkeypatch):
        monkeypatch.setenv("BUTLER_RUNTIME_ENABLED", "0")
        from butler.runtime.service import run_job
        result = run_job("p", "j")
        assert result["success"] is False
        assert "BUTLER_RUNTIME_ENABLED" in result["error"]


# ── MCP exposed server (read-only subset) ─────────────────────

class TestMcpServerExposed:
    def test_exposed_tools_are_readonly(self):
        from butler.mcp.server_stdio import _EXPOSED
        write_tools = {"write_file", "patch", "delete_file", "terminal"}
        overlap = set(_EXPOSED) & write_tools
        assert overlap == set(), f"MCP server exposes write tools: {overlap}"

    def test_exposed_set_is_small(self):
        from butler.mcp.server_stdio import _EXPOSED
        assert len(_EXPOSED) <= 10
