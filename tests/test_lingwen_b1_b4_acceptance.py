"""B1-B4 灵文样板运营验收 — 自动化验收门控.

Acceptance criteria from轨道 B (post-consolidation-roadmap):
  B1: 维护态/新书态双剧本 — role=lead, lifecycle-aware
  B2: 微信测试闭环 — Lead 不亲自 terminal/write，委派 dev
  B3: Lead 触发只读 job 场景 — run_runtime_job 在工具集中
  B4: 试点文档收口 — project.yaml 结构正确
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import pytest


@dataclass
class FakeProject:
    lead: Optional[bool] = None
    pack: str = ""
    lifecycle: str = ""
    tools: list[str] | None = None


class TestB1DualPlaybook:
    """B1: 维护态/新书态双剧本 — Lead role 在 gateway 正确判定."""

    def test_lingwen_default_is_lead(self):
        from butler.project.lead import gateway_loop_role
        assert gateway_loop_role("灵文1号") == "lead"

    def test_lingwen_alt_name_is_lead(self):
        from butler.project.lead import gateway_loop_role
        assert gateway_loop_role("灵文1") == "lead"

    def test_explicit_lead_true(self):
        from butler.project.lead import gateway_loop_role
        proj = FakeProject(lead=True)
        assert gateway_loop_role("any_project", project=proj) == "lead"

    def test_explicit_lead_false_overrides(self):
        from butler.project.lead import gateway_loop_role
        proj = FakeProject(lead=False)
        assert gateway_loop_role("灵文1号", project=proj) == "butler"

    def test_novel_factory_pack_is_lead(self):
        from butler.project.lead import gateway_loop_role
        proj = FakeProject(pack="novel-factory")
        assert gateway_loop_role("some_novel", project=proj) == "lead"

    def test_non_lead_project_is_butler(self):
        from butler.project.lead import gateway_loop_role
        proj = FakeProject()
        assert gateway_loop_role("普通项目", project=proj) == "butler"

    def test_is_lead_project_consistent_with_role(self):
        from butler.project.lead import gateway_loop_role, is_lead_project
        proj = FakeProject(lead=True)
        assert is_lead_project("x", project=proj) == (gateway_loop_role("x", project=proj) == "lead")


class TestB2LeadToolBoundary:
    """B2: Lead 不亲自 write/terminal/PIM — 工具集验证."""

    def test_lead_extra_no_write_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        write_tools = {"write_file", "patch", "create_file", "delete_file", "multi_edit"}
        assert _LEAD_EXTRA_TOOLS.isdisjoint(write_tools), (
            f"Lead extra tools contain write tools: {_LEAD_EXTRA_TOOLS & write_tools}"
        )

    def test_lead_extra_no_terminal_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        shell_tools = {"terminal", "run_command", "shell", "execute_command"}
        assert _LEAD_EXTRA_TOOLS.isdisjoint(shell_tools)

    def test_lead_extra_no_pim_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        try:
            from butler.tools.pim_schema import ALL_PIM_TOOLS
            pim_set = set(ALL_PIM_TOOLS)
        except ImportError:
            pim_set = {"memo_add", "memo_search", "contacts_add", "contacts_search"}
        assert _LEAD_EXTRA_TOOLS.isdisjoint(pim_set), (
            f"Lead extra tools contain PIM: {_LEAD_EXTRA_TOOLS & pim_set}"
        )

    def test_lead_has_delegate_task(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert "delegate_task" in _LEAD_EXTRA_TOOLS

    def test_lead_read_tools_are_read_only(self):
        from butler.tools.project_tools import _LEAD_READ_TOOLS
        assert "read_file" in _LEAD_READ_TOOLS
        assert "list_directory" in _LEAD_READ_TOOLS
        assert "search_files" in _LEAD_READ_TOOLS
        assert "write_file" not in _LEAD_READ_TOOLS


class TestB3LeadReadOnlyJobs:
    """B3: Lead 可触发只读 runtime job — 工具可用性验证."""

    def test_lead_has_runtime_job_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert "list_runtime_jobs" in _LEAD_EXTRA_TOOLS
        assert "run_runtime_job" in _LEAD_EXTRA_TOOLS

    def test_lead_has_workflow_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert "run_workflow" in _LEAD_EXTRA_TOOLS
        assert "list_workflows" in _LEAD_EXTRA_TOOLS

    def test_lead_has_skill_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert "skills_list" in _LEAD_EXTRA_TOOLS
        assert "skill_view" in _LEAD_EXTRA_TOOLS

    def test_lead_has_memory_tools(self):
        from butler.tools.project_tools import _LEAD_EXTRA_TOOLS
        assert "butler_remember" in _LEAD_EXTRA_TOOLS
        assert "butler_recall" in _LEAD_EXTRA_TOOLS


class TestB4ProjectStructure:
    """B4: 试点文档收口 — 项目配置格式正确."""

    def test_lead_mode_switch_suffix(self):
        from butler.project.lead import lead_mode_switch_suffix
        proj = FakeProject(lead=True)
        suffix = lead_mode_switch_suffix("灵文1号", project=proj)
        assert isinstance(suffix, str)

    def test_butler_role_all_tools_consistent(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS, _LEAD_EXTRA_TOOLS
        butler_only = _BUTLER_EXTRA_TOOLS - _LEAD_EXTRA_TOOLS
        lead_only = _LEAD_EXTRA_TOOLS - _BUTLER_EXTRA_TOOLS
        assert "delegate_task" not in butler_only or "delegate_task" in _LEAD_EXTRA_TOOLS

    def test_lead_and_butler_disjoint_on_write(self):
        from butler.tools.project_tools import _BUTLER_EXTRA_TOOLS, _LEAD_EXTRA_TOOLS
        write_tools = {"write_file", "patch", "create_file", "delete_file", "terminal"}
        assert _BUTLER_EXTRA_TOOLS.isdisjoint(write_tools), (
            "Butler extra should not include write tools either"
        )
        assert _LEAD_EXTRA_TOOLS.isdisjoint(write_tools)

    def test_lead_project_names_env_override(self, monkeypatch):
        monkeypatch.setenv("BUTLER_LEAD_PROJECTS", "TestProj,AnotherProj")
        from butler.project.lead import lead_project_names
        names = lead_project_names()
        assert "TestProj" in names
        assert "AnotherProj" in names
        assert "灵文1号" not in names
