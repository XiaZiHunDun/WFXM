"""Premise T8 verification: Butler-Delegate separation.

Validates:
  - _BUTLER_EXTRA_TOOLS does NOT contain write/shell tools
  - _LEAD_EXTRA_TOOLS does NOT contain write/shell/PIM tools
  - PIM tools are exclusive to butler role (not in lead or delegate)
  - DELEGATE_BLOCKED_TOOLS blocks sensitive tools from sub-agents

Theoretical reference: T8' (管家-委派分离), §2.4, §5 T8'
"""

from __future__ import annotations

import pytest


_WRITE_TOOLS = frozenset({
    "write_file", "patch", "edit_file", "delete_file",
    "terminal", "run_shell",
})

_PIM_TOOLS = frozenset({
    "memo_add", "memo_list", "memo_search",
    "contact_add", "contact_find",
    "expense_add", "expense_summary",
    "habit_create", "habit_checkin", "habit_list", "habit_stats",
})


class TestButlerExtraToolsNoWrite:
    """T8a: _BUTLER_EXTRA_TOOLS must not include file-write or shell tools."""

    def test_no_write_tools(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS
        overlap = _BUTLER_EXTRA_TOOLS & _WRITE_TOOLS
        assert overlap == set(), f"BUTLER_EXTRA_TOOLS contains write tools: {overlap}"

    def test_contains_delegate(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS
        assert "delegate_task" in _BUTLER_EXTRA_TOOLS

    def test_contains_pim_tools(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS
        for tool in _PIM_TOOLS:
            assert tool in _BUTLER_EXTRA_TOOLS, f"Missing PIM tool: {tool}"

    def test_is_frozenset(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS
        assert isinstance(_BUTLER_EXTRA_TOOLS, frozenset)


class TestLeadExtraToolsNoWriteNoPIM:
    """T8b: _LEAD_EXTRA_TOOLS must not include write/shell tools or PIM tools."""

    def test_no_write_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        overlap = _LEAD_EXTRA_TOOLS & _WRITE_TOOLS
        assert overlap == set(), f"LEAD_EXTRA_TOOLS contains write tools: {overlap}"

    def test_no_pim_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        overlap = _LEAD_EXTRA_TOOLS & _PIM_TOOLS
        assert overlap == set(), f"LEAD_EXTRA_TOOLS contains PIM tools: {overlap}"

    def test_contains_delegate(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert "delegate_task" in _LEAD_EXTRA_TOOLS

    def test_is_frozenset(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert isinstance(_LEAD_EXTRA_TOOLS, frozenset)


class TestDelegateBlockedTools:
    """T8c: DELEGATE_BLOCKED_TOOLS blocks sensitive capabilities from sub-agents."""

    def test_delegate_blocked_is_frozenset(self):
        from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
        assert isinstance(DELEGATE_BLOCKED_TOOLS, frozenset)

    def test_delegate_task_is_blocked(self):
        from butler.delegate.policy import DELEGATE_BLOCKED_TOOLS
        assert "delegate_task" in DELEGATE_BLOCKED_TOOLS

    def test_pim_tools_not_in_project_default_tools(self):
        """PIM tools are in _BUTLER_EXTRA_TOOLS but not in standard project tools.
        Sub-agents get tools from project definitions, not _BUTLER_EXTRA_TOOLS,
        so PIM tools don't leak to sub-agents."""
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS, _LEAD_EXTRA_TOOLS
        pim_only_in_butler = _PIM_TOOLS - _LEAD_EXTRA_TOOLS
        assert pim_only_in_butler == _PIM_TOOLS, \
            f"PIM tools leaked to LEAD_EXTRA_TOOLS: {_PIM_TOOLS & _LEAD_EXTRA_TOOLS}"


class TestButlerRuntimeAllowlist:
    """T8e: gateway butler role must not inherit mutating tools from project.yaml (A3/T8)."""

    def _software_project(self, tmp_path, tools: list[str]):
        import yaml
        from butler.project import Project

        d = tmp_path / "sw"
        d.mkdir()
        (d / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "sw",
                    "workspace": str(d),
                    "tools": tools,
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return Project.from_yaml(d / "project.yaml")

    def test_butler_strips_write_shell_from_project_yaml(self, tmp_path):
        from butler.tools.project_tools import allowed_tool_names_for_project

        proj = self._software_project(
            tmp_path,
            ["read_file", "write_file", "patch", "terminal", "delegate_task", "git_status"],
        )
        allowed = allowed_tool_names_for_project(proj, role="butler")
        assert allowed is not None
        assert "read_file" in allowed
        assert "git_status" in allowed
        assert "delegate_task" in allowed
        assert "memo_add" in allowed
        overlap = allowed & _WRITE_TOOLS
        assert overlap == set(), f"butler allowlist leaked write tools: {overlap}"

    def test_lead_and_butler_both_strip_write(self, tmp_path):
        from butler.tools.project_tools import allowed_tool_names_for_project

        proj = self._software_project(tmp_path, ["read_file", "write_file", "patch"])
        for role in ("butler", "lead"):
            allowed = allowed_tool_names_for_project(proj, role=role)
            assert "write_file" not in allowed, role
            assert "patch" not in allowed, role


class TestRoleDeterminism:
    """T8d: gateway_loop_role returns deterministic role for any project."""

    def test_default_is_butler(self):
        from butler.project.lead import gateway_loop_role
        role = gateway_loop_role("random_project_xyz")
        assert role == "butler"

    def test_lead_project_returns_lead(self):
        from butler.project.lead import gateway_loop_role, _DEFAULT_LEAD_PROJECTS
        if _DEFAULT_LEAD_PROJECTS:
            name = next(iter(_DEFAULT_LEAD_PROJECTS))
            role = gateway_loop_role(name)
            assert role == "lead"

    def test_explicit_lead_true(self):
        from butler.project.lead import gateway_loop_role

        class FakeProject:
            lead = True
            pack = None

        role = gateway_loop_role("any", project=FakeProject())
        assert role == "lead"

    def test_explicit_lead_false(self):
        from butler.project.lead import gateway_loop_role

        class FakeProject:
            lead = False
            pack = None

        role = gateway_loop_role("灵文1号", project=FakeProject())
        assert role == "butler"

    def test_novel_factory_is_lead(self):
        from butler.project.lead import gateway_loop_role

        class FakeProject:
            lead = None
            pack = "novel-factory"

        role = gateway_loop_role("some_novel", project=FakeProject())
        assert role == "lead"
