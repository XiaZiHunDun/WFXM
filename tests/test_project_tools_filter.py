"""Sprint 2: project.yaml tool allowlists."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project import Project
from butler.project.manager import ProjectManager
from butler.tools.project_tools import (
    allowed_tool_names_for_project,
    canonical_tool_name,
    get_tool_definitions_for_project,
)
from butler.tools.registry import get_tool_definitions


def _project_with_tools(tmp_path: Path) -> Project:
    proj_dir = tmp_path / "demo"
    proj_dir.mkdir()
    (proj_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "demo",
                "type": "software",
                "description": "demo",
                "workspace": str(proj_dir),
                "tools": [
                    "read_file",
                    "write_file",
                    "edit_file",
                    "search_code",
                    "run_shell",
                    "skill_list",
                ],
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    return Project.from_yaml(proj_dir / "project.yaml")


@pytest.mark.module_test
class TestProjectToolAliases:
    def test_canonical_names(self):
        assert canonical_tool_name("edit_file") == "patch"
        assert canonical_tool_name("search_code") == "search_files"
        assert canonical_tool_name("run_shell") == "terminal"
        assert canonical_tool_name("skill_list") == "skills_list"


@pytest.mark.module_test
class TestProjectToolFilter:
    def test_butler_gets_delegate_and_skills(self, tmp_path):
        proj = _project_with_tools(tmp_path)
        allowed = allowed_tool_names_for_project(proj, role="butler")
        assert "read_file" in allowed
        assert "search_files" in allowed
        assert "delegate_task" in allowed
        assert "skills_list" in allowed
        assert "butler_remember" in allowed
        assert "butler_recall" in allowed
        assert "patch" not in allowed
        assert "write_file" not in allowed
        assert "terminal" not in allowed

    def test_dev_role_excludes_delegate(self, tmp_path):
        proj = _project_with_tools(tmp_path)
        allowed = allowed_tool_names_for_project(proj, role="dev")
        assert "delegate_task" not in allowed
        assert "read_file" in allowed

    def test_filtered_definitions_subset(self, tmp_path):
        proj = _project_with_tools(tmp_path)
        filtered = get_tool_definitions_for_project(proj, role="dev")
        names = {t["function"]["name"] for t in filtered}
        assert "read_file" in names
        assert "delegate_task" not in names
        assert names.issubset({t["function"]["name"] for t in get_tool_definitions()})

    def test_empty_tools_list_means_unrestricted(self, tmp_path):
        proj_dir = tmp_path / "open"
        proj_dir.mkdir()
        (proj_dir / "project.yaml").write_text(
            yaml.safe_dump({"name": "open", "workspace": str(proj_dir)}, allow_unicode=True),
            encoding="utf-8",
        )
        proj = Project.from_yaml(proj_dir / "project.yaml")
        assert allowed_tool_names_for_project(proj, role="butler") is None


@pytest.mark.integration
class TestGatewayUsesProjectTools:
    def test_handler_loop_tools_match_project_yaml(self, tmp_path, monkeypatch, tmp_butler_home):
        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        proj = projects_dir / "narrow"
        proj.mkdir()
        (proj / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "narrow",
                    "type": "software",
                    "description": "narrow tools",
                    "workspace": str(proj),
                    "tools": ["read_file", "write_file"],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        from tests.gateway.test_gateway_handler import _reset_singletons

        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        _reset_singletons()
        reload_butler_settings()

        from butler.gateway.message_handler import ButlerMessageHandler

        handler = ButlerMessageHandler(channel="test")
        handler._orchestrator.project_manager.switch_project("narrow")
        loop = handler._create_loop_for_session("test:u1:narrow")
        names = {t["function"]["name"] for t in loop.tools}
        assert "read_file" in names
        assert "delegate_task" in names
        assert "write_file" not in names
        assert "terminal" not in names
        assert "patch" not in names
