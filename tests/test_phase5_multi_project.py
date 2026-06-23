"""Phase 5 — Track C multi-project onboarding."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestC1ExternalRepo:
    def test_cli_register_git_url_detection(self):
        from butler.cli.projects_cli import _is_git_url

        assert _is_git_url("https://github.com/user/repo.git")
        assert not _is_git_url("projects/MyApp")

    def test_wechat_register_git_clone(self, tmp_path, monkeypatch):
        from butler.config import ButlerSettings
        from butler.gateway.commands.project_handlers import _project_register_wechat

        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(tmp_path / "projects"))
        settings = ButlerSettings()
        settings.projects_dir = tmp_path / "projects"
        settings.projects_dir.mkdir(parents=True)

        orch = MagicMock()
        orch.project_manager.register_workspace.return_value = MagicMock(
            name="ext-repo",
            workspace=tmp_path / "projects" / "repo",
        )

        with patch("butler.gateway.owner_gate.is_gateway_owner", return_value=True), \
             patch("butler.config.get_butler_settings", return_value=settings), \
             patch(
                 "butler.gateway.commands.project_handlers._clone_git_repo",
                 return_value=(True, str(tmp_path / "projects" / "repo")),
             ):
            out = _project_register_wechat(
                orch,
                ["外部仓库", "https://github.com/user/repo.git"],
                platform="wechat",
                external_id="owner1",
                session_key="s1",
            )
        assert "已登记" in out
        orch.project_manager.register_workspace.assert_called_once()


class TestC2DefaultProjectPolicy:
    def test_format_default_project_policy_lines(self, monkeypatch):
        from butler.project.meta import format_default_project_policy_lines

        monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "灵文1号")
        orch = MagicMock()
        orch.project_manager.resolve_active_project_name.return_value = "灵文1号"
        lines = format_default_project_policy_lines(orch, "wechat:u1")
        text = "\n".join(lines)
        assert "BUTLER_DEFAULT_PROJECT" in text
        assert "灵文1号" in text

    def test_health_report_includes_default_policy(self, monkeypatch):
        from butler.ops.health_report import HealthReportInput, build_health_report

        monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "演示试点")
        orch = MagicMock()
        orch.project_manager.get_current.return_value = None
        orch.project_manager.resolve_active_project_name.return_value = "(无)"
        orch._settings = MagicMock()
        report = build_health_report(
            HealthReportInput(
                session_key="s1",
                health=None,
                tool_summary={"total": 0, "failed": 0, "codes": []},
                mem_stats={},
                orchestrator=orch,
            )
        )
        assert "默认项目策略" in report


class TestC3SecondLead:
    def test_demo_pilot_yaml_has_lead(self):
        import yaml

        path = Path("projects/DemoPilot/project.yaml")
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert data.get("lead") is True

    def test_demo_pilot_is_lead(self):
        from butler.project.lead import is_lead_project
        from butler.project.model import Project

        proj = Project.from_yaml(Path("projects/DemoPilot/project.yaml"))
        assert is_lead_project(proj.name, project=proj)


class TestC4ProjectCreateTemplate:
    def test_create_with_knowledge_light_template(self, tmp_path, monkeypatch):
        from butler.config import reload_butler_settings
        from butler.project.manager import ProjectManager, get_project_manager

        projects_dir = tmp_path / "projects"
        projects_dir.mkdir()
        monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path / "butler_home"))
        ProjectManager._instance = None
        reload_butler_settings()

        mgr = get_project_manager()
        created = mgr.create_project(
            "KbPilot",
            "content",
            "",
            display_name="知识试点",
            template="knowledge-light",
        )
        assert created is not None
        assert (created.workspace / "project.yaml").is_file()
        assert created.type == "content" or created.name == "知识试点"

    def test_wechat_create_usage_hint(self):
        from butler.gateway.commands.project_handlers import _project_create_wechat

        orch = MagicMock()
        with patch("butler.gateway.owner_gate.is_gateway_owner", return_value=True):
            out = _project_create_wechat(orch, [], platform="wechat", external_id="o1")
        assert "software-default" in out
        assert "novel-factory" in out
