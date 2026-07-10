"""Project Lead phase 2 — dedicated gateway loop and tool allowlist."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.project import Project
from butler.project.lead import (
    gateway_loop_role,
    is_lead_project,
    lead_mode_switch_suffix,
)
from butler.tools.project_tools import allowed_tool_names_for_project, canonical_tool_name


@pytest.mark.module_test
class TestLeadProjectDetection:
    def test_lingwen_is_lead(self):
        assert is_lead_project("灵文1号")
        assert gateway_loop_role("灵文1号") == "lead"
        assert gateway_loop_role("Other") == "butler"

    def test_switch_suffix(self):
        assert "厂长模式" in lead_mode_switch_suffix("灵文1号")
        assert lead_mode_switch_suffix("demo") == ""


@pytest.mark.module_test
class TestLeadToolAllowlist:
    def _project(self, tmp_path: Path) -> Project:
        d = tmp_path / "lw"
        d.mkdir()
        (d / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "灵文1号",
                    "workspace": str(d),
                    "tools": [
                        "read_file",
                        "write_file",
                        "edit_file",
                        "run_shell",
                        "search_code",
                    ],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        return Project.from_yaml(d / "project.yaml")

    def test_lead_excludes_write_and_shell(self, tmp_path):
        proj = self._project(tmp_path)
        allowed = allowed_tool_names_for_project(proj, role="lead")
        assert allowed is not None
        assert "read_file" in allowed
        assert "search_files" in allowed
        assert canonical_tool_name("search_code") in allowed
        assert "delegate_task" in allowed
        assert "run_workflow" in allowed
        assert "write_file" not in allowed
        assert "patch" not in allowed
        assert "terminal" not in allowed

    def test_lead_honors_mcp_opt_in(self, tmp_path):
        d = tmp_path / "lw-mcp"
        d.mkdir()
        (d / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "灵文MCP",
                    "workspace": str(d),
                    "tools": ["read_file", "write_file", "mcp_*"],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        proj = Project.from_yaml(d / "project.yaml")
        allowed = allowed_tool_names_for_project(proj, role="lead")
        assert allowed is not None
        assert "mcp_*" in allowed
        assert "write_file" not in allowed

    def test_lead_honors_web_search_opt_in(self, tmp_path):
        d = tmp_path / "lw-search"
        d.mkdir()
        (d / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "灵文Search",
                    "workspace": str(d),
                    "tools": ["read_file", "write_file", "web_search"],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        proj = Project.from_yaml(d / "project.yaml")
        allowed = allowed_tool_names_for_project(proj, role="lead")
        assert allowed is not None
        assert "web_search" in allowed
        assert "write_file" not in allowed

    def test_butler_role_unrestricted_on_project(self, tmp_path):
        proj = self._project(tmp_path)
        assert allowed_tool_names_for_project(proj, role="butler") is None


@pytest.mark.module_test
class TestLeadLoopFactory:
    def test_gateway_creates_lead_loop_for_lingwen_session(self, tmp_path, monkeypatch):
        from butler.config import reload_butler_settings
        from butler.project.manager import ProjectManager

        ProjectManager._instance = None
        reload_butler_settings()
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path / "projects"))
        proj_dir = tmp_path / "projects" / "LingWen1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "灵文1号",
                    "lead": True,
                    "tools": ["read_file", "write_file", "patch"],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )

        from butler.gateway.message_handler import ButlerMessageHandler
        from butler.session.keys import build_session_key

        handler = ButlerMessageHandler(channel="test")
        sk = build_session_key(
            platform="wechat",
            chat_id="user@test",
            project="灵文1号",
        )
        handler._orchestrator.project_manager.switch_project_for_chat(
            platform="wechat",
            chat_id="user@test",
            name="灵文1号",
        )
        loop = handler._create_loop_for_session(sk)
        assert "厂长" in (loop.system_prompt or "") or "Lead" in (loop.system_prompt or "")
        names = {t["function"]["name"] for t in loop.tools}
        assert "delegate_task" in names
        assert "write_file" not in names

    def test_build_lead_system_prompt(self, tmp_path, monkeypatch):
        from butler.config import reload_butler_settings
        from butler.project.manager import ProjectManager

        ProjectManager._instance = None
        reload_butler_settings()
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path / "projects"))
        proj_dir = tmp_path / "projects" / "LingWen1"
        proj_dir.mkdir(parents=True)
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump(
                {"name": "灵文1号", "workspace": str(proj_dir), "tools": ["read_file"]},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        from butler.orchestrator import ButlerOrchestrator

        orch = ButlerOrchestrator(channel="test")
        orch.project_manager.switch_project("灵文1号")
        text = orch.build_lead_system_prompt(session_key="wechat:u@x:灵文1号")
        assert "灵文1号" in text
        assert "delegate_task" in text
        assert "workflow_state" in text
