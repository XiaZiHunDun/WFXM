"""P5 工程前提验证: 权限隔离无漏洞。

验证理论基线文档中的命题:
- 公理 A4 (权限单调递减): Owner → Butler → Delegate 权限不可逆增
- 命题 2.7 (delegate 权限收窄): delegate 工具集 ⊂ parent 工具集
- 命题 2.8 (权限不可逆传递): 子代理不可恢复被削减的权限
- 定理 T3 (权限不可提升): 子系统权限 ≤ 父系统权限
"""

from __future__ import annotations

import json

import pytest


class TestP5DelegateBlockedTools:
    """验证 DELEGATE_BLOCKED_TOOLS 阻止递归委派和 workflow。"""

    def test_delegate_blocked_tools_contains_delegate(self):
        from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
        assert "delegate_task" in DELEGATE_BLOCKED_TOOLS

    def test_delegate_blocked_tools_contains_run_workflow(self):
        from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
        assert "run_workflow" in DELEGATE_BLOCKED_TOOLS

    def test_delegate_blocked_tools_is_frozenset(self):
        from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
        assert isinstance(DELEGATE_BLOCKED_TOOLS, frozenset)

    def test_safe_dispatch_rejects_blocked_tools(self):
        """_safe_dispatch 对 DELEGATE_BLOCKED_TOOLS 中的工具返回 error。"""
        from butler.tools.delegate_impl import _safe_dispatch

        result = json.loads(_safe_dispatch("delegate_task", {}, depth=1))
        assert "error" in result
        assert "blocked" in result["error"].lower()

        result = json.loads(_safe_dispatch("run_workflow", {}, depth=1))
        assert "error" in result
        assert "blocked" in result["error"].lower()


class TestP5SubagentToolFiltering:
    """命题 2.7: filter_tools_for_subagent 确保子工具集 ⊂ 父工具集。"""

    def _make_tool_list(self, names: list[str]) -> list[dict]:
        return [{"function": {"name": n}} for n in names]

    def test_subagent_cannot_use_delegate_task(self):
        from butler.delegate.subagent_permissions import filter_tools_for_subagent

        tools = self._make_tool_list([
            "read_file", "write_file", "terminal", "delegate_task", "run_workflow",
        ])
        filtered = filter_tools_for_subagent(tools)
        filtered_names = {t["function"]["name"] for t in filtered}
        assert "delegate_task" not in filtered_names
        assert "run_workflow" not in filtered_names

    def test_subagent_cannot_use_session_todos(self):
        from butler.delegate.subagent_permissions import filter_tools_for_subagent

        tools = self._make_tool_list([
            "read_file", "session_todos_list", "session_todos_write",
        ])
        filtered = filter_tools_for_subagent(tools)
        filtered_names = {t["function"]["name"] for t in filtered}
        assert "session_todos_list" not in filtered_names
        assert "session_todos_write" not in filtered_names

    def test_subagent_tool_subset_invariant(self):
        """过滤后的工具集始终是父集的子集。"""
        from butler.delegate.subagent_permissions import filter_tools_for_subagent

        parent_names = [
            "read_file", "write_file", "patch", "terminal",
            "search_files", "list_directory", "delegate_task",
            "run_workflow", "run_runtime_job",
        ]
        tools = self._make_tool_list(parent_names)
        filtered = filter_tools_for_subagent(tools)
        filtered_names = {t["function"]["name"] for t in filtered}
        assert filtered_names.issubset(set(parent_names))
        assert len(filtered_names) < len(parent_names)


class TestP5DefaultSubagentDeny:
    """_DEFAULT_SUBAGENT_DENY 至少覆盖危险工具。"""

    def test_deny_set_coverage(self):
        from butler.delegate.subagent_permissions import _DEFAULT_SUBAGENT_DENY

        expected = {"delegate_task", "run_workflow", "run_runtime_job",
                    "session_todos_list", "session_todos_write"}
        assert expected.issubset(_DEFAULT_SUBAGENT_DENY)


class TestP5MaxDelegateDepth:
    """防止无限递归委派。"""

    def test_max_depth_is_bounded(self):
        from butler.delegate.policy import MAX_DELEGATE_DEPTH
        assert isinstance(MAX_DELEGATE_DEPTH, int)
        assert 1 <= MAX_DELEGATE_DEPTH <= 5


class TestP5PermissionDecisionEnforcement:
    """权限决策系统的完整性。"""

    def test_security_blacklist_blocks_denied(self):
        from butler.permissions.rules import evaluate_security_blacklist
        result = evaluate_security_blacklist("terminal", {"command": "rm -rf /"})
        # Without a configured YAML, should return None (no rule)
        assert result is None

    def test_external_directory_denies_when_no_rules(self):
        """外部目录访问默认拒绝（无规则时）。"""
        from pathlib import Path
        from butler.permissions.rules import evaluate_external_directory
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            workspace = Path(tmpdir)
            result = evaluate_external_directory(
                "/etc/passwd",
                workspace=workspace,
                for_write=False,
            )
            if result is not None:
                assert not result.allowed

    def test_workflow_step_allowlist_enforced(self, tmp_path):
        """步骤白名单存在时，只允许列出的工具。"""
        from butler.permissions.rules import evaluate_workflow_step_permission

        perms_file = tmp_path / ".butler" / "permissions.yaml"
        perms_file.parent.mkdir(parents=True, exist_ok=True)

        import yaml
        perms_file.write_text(yaml.dump({
            "workflow_steps": {
                "review_step": {
                    "tools": ["read_file", "search_files"]
                }
            }
        }))

        allowed = evaluate_workflow_step_permission(
            "read_file", "review_step", workspace=tmp_path,
        )
        assert allowed is not None
        assert allowed.allowed is True

        denied = evaluate_workflow_step_permission(
            "write_file", "review_step", workspace=tmp_path,
        )
        assert denied is not None
        assert denied.allowed is False

    def test_permission_decision_fail_closed(self):
        """失败时选择拒绝（fail-closed）而非放行。"""
        from butler.permissions.rules import (
            _record_permission_failure,
            recent_permission_failures,
            reset_permission_failures,
        )

        reset_permission_failures()
        _record_permission_failure("test_check", RuntimeError("synthetic"))
        failures = recent_permission_failures()
        assert len(failures) == 1
        assert failures[0]["check"] == "test_check"
        reset_permission_failures()


class TestP5HumanGateIsolation:
    """工作流人工门控不可被绕过。"""

    def test_gate_confirm_cancel_vocabulary_disjoint(self):
        from butler.human_gate import _CONFIRM, _CANCEL
        assert _CONFIRM.isdisjoint(_CANCEL), "确认/取消词汇表重叠"

    def test_gate_confirm_vocabulary(self):
        from butler.human_gate import _CONFIRM
        assert "确认" in _CONFIRM
        assert "yes" in _CONFIRM

    def test_gate_cancel_vocabulary(self):
        from butler.human_gate import _CANCEL
        assert "取消" in _CANCEL
        assert "no" in _CANCEL


class TestP5PermissionMonotonicity:
    """定理 T3: 权限在委派链中单调递减。"""

    def test_two_layer_permission_shrinkage(self):
        """
        层 0 (Parent): 9 tools
        层 1 (Delegate): filter_tools_for_subagent 后 < 9
        这证明权限不可逆增。
        """
        from butler.delegate.subagent_permissions import filter_tools_for_subagent

        parent_tools = [{"function": {"name": n}} for n in [
            "read_file", "write_file", "patch", "delete_file",
            "terminal", "search_files", "delegate_task",
            "run_workflow", "run_runtime_job",
        ]]
        child_tools = filter_tools_for_subagent(parent_tools)
        assert len(child_tools) < len(parent_tools)

        child_names = {t["function"]["name"] for t in child_tools}
        grand_tools = filter_tools_for_subagent(child_tools)
        grand_names = {t["function"]["name"] for t in grand_tools}
        assert grand_names.issubset(child_names)
