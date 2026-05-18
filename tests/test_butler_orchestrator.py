"""Tests for butler.orchestrator and butler.report."""

import tempfile
from pathlib import Path

import pytest
import yaml

from butler.report import (
    AgentReport,
    Change,
    format_detail,
    format_for_butler_tool_result,
    format_for_cli,
    format_for_wechat,
)


class TestAgentReport:
    def test_roundtrip(self):
        report = AgentReport(
            headline="Test report",
            changes=[Change("file.py", "created", "New file")],
            decisions=["Use Python"],
            issues=["Missing tests"],
            summary="Created a new file",
        )
        d = report.to_dict()
        report2 = AgentReport.from_dict(d)
        assert report2.headline == report.headline
        assert len(report2.changes) == 1
        assert report2.changes[0].file == "file.py"

    def test_from_dict_with_desc_key(self):
        d = {
            "headline": "test",
            "changes": [{"file": "a.py", "action": "modified", "desc": "changed"}],
        }
        report = AgentReport.from_dict(d)
        assert report.changes[0].description == "changed"


class TestReportFormatting:
    @pytest.fixture
    def sample_report(self):
        return AgentReport(
            headline="完成认证模块",
            changes=[
                Change("auth.py", "created", "JWT认证"),
                Change("middleware.py", "modified", "鉴权中间件"),
            ],
            decisions=["使用JWT"],
            issues=["需要密钥配置"],
            summary="完成登录注册",
        )

    def test_format_cli(self, sample_report):
        text = format_for_cli(sample_report)
        assert "完成认证模块" in text
        assert "auth.py" in text

    def test_format_wechat(self, sample_report):
        text = format_for_wechat(sample_report)
        assert "完成认证模块" in text
        assert "新建1个文件" in text
        assert "详细" in text

    def test_format_detail(self, sample_report):
        text = format_detail(sample_report)
        assert "JWT认证" in text
        assert "使用JWT" in text

    def test_format_detail_section(self, sample_report):
        text = format_detail(sample_report, section="changes")
        assert "auth.py" in text

    def test_format_tool_result(self, sample_report):
        d = format_for_butler_tool_result(sample_report)
        assert d["headline"] == "完成认证模块"
        assert d["changes_count"] == 2


class TestOrchestrator:
    def test_build_system_prompt(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            projects_dir = Path(td) / "projects"
            projects_dir.mkdir()
            p1 = projects_dir / "TestProj"
            p1.mkdir()
            (p1 / "project.yaml").write_text(
                yaml.safe_dump({"name": "TestProj", "type": "software", "description": "test"})
            )
            monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))

            from butler.config import reload_butler_settings
            from butler.project_manager import ProjectManager
            ProjectManager._instance = None
            reload_butler_settings()

            from butler.orchestrator import ButlerOrchestrator
            orch = ButlerOrchestrator()
            prompt = orch.build_system_prompt()
            assert "莎丽" in prompt or "管家" in prompt
            assert "TestProj" in prompt
            ProjectManager._instance = None

    def test_inject_skill_context(self, monkeypatch):
        monkeypatch.delenv("MINIMAX_API_KEY", raising=False)
        with tempfile.TemporaryDirectory() as td:
            monkeypatch.setenv("BUTLER_HOME", td)
            projects_dir = Path(td) / "projects"
            projects_dir.mkdir()
            monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))

            from butler.config import reload_butler_settings
            from butler.project_manager import ProjectManager
            ProjectManager._instance = None
            reload_butler_settings()

            from butler.orchestrator import ButlerOrchestrator
            orch = ButlerOrchestrator()
            result = orch.inject_skill_context("run python tests")
            assert isinstance(result, str)
            ProjectManager._instance = None
