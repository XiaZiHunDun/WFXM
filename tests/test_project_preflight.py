"""Tests for butler.project_preflight."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project.manager import ProjectManager
from butler.project.preflight import CheckLevel, format_report, run_preflight


def _reset_pm() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(root))
    _reset_pm()
    yield root
    _reset_pm()


@pytest.mark.unit
class TestProjectPreflight:
    def test_missing_path_fails(self, projects_dir):
        report = run_preflight(
            projects_dir / "nope",
            projects_dir=projects_dir,
        )
        assert not report.ok
        assert any(i.code == "path_missing" for i in report.items)

    def test_missing_yaml_fails(self, projects_dir):
        ws = projects_dir / "empty"
        ws.mkdir()
        report = run_preflight(ws, projects_dir=projects_dir)
        assert not report.ok
        assert any(i.code == "missing_project_yaml" for i in report.items)

    def test_software_project_ok(self, projects_dir):
        ws = projects_dir / "app1"
        ws.mkdir()
        (ws / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (ws / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "应用一",
                    "type": "software",
                    "tools": ["read_file"],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        (ws / ".butler" / "memory").mkdir(parents=True)
        (ws / ".butler" / "memory" / "MEMORY.md").write_text("# mem\n", encoding="utf-8")

        report = run_preflight(ws, projects_dir=projects_dir)
        assert report.ok
        assert report.project_name == "应用一"
        assert report.suggested_template == "software-default"
        assert report.registered is True

    def test_summarize_fix_verdict(self, projects_dir):
        ws = projects_dir / "bad"
        ws.mkdir()
        report = run_preflight(ws, projects_dir=projects_dir)
        s = report.summarize()
        assert s["verdict"] == "fix"
        assert s["fail_count"] >= 1

    def test_format_report_has_tier_headline(self, projects_dir):
        ws = projects_dir / "app2"
        ws.mkdir()
        (ws / "project.yaml").write_text(
            yaml.safe_dump(
                {"name": "应用二", "type": "software", "tools": ["read_file"]},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        report = run_preflight(ws, projects_dir=projects_dir)
        text = format_report(report)
        assert text.startswith("【")

    def test_novel_factory_template_suggested(self, projects_dir):
        ws = projects_dir / "nf"
        nf = ws / "novel-factory"
        nf.mkdir(parents=True)
        (nf / "workflow_state.json").write_text(
            '{"phase": "PHASE_COMPLETE"}',
            encoding="utf-8",
        )
        (ws / "project.yaml").write_text(
            yaml.safe_dump(
                {"name": "书厂", "type": "content", "tools": ["read_file"]},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        report = run_preflight(ws, projects_dir=projects_dir)
        assert report.suggested_template == "novel-factory"
        assert "pack:novel-factory" in report.suggested_tags
        assert "lifecycle:complete" in report.suggested_tags

    def test_knowledge_light_when_no_code(self, projects_dir):
        ws = projects_dir / "docs_only"
        ws.mkdir()
        (ws / "docs").mkdir()
        (ws / "project.yaml").write_text(
            yaml.safe_dump({"name": "备忘", "type": "content"}, allow_unicode=True),
            encoding="utf-8",
        )
        report = run_preflight(ws, projects_dir=projects_dir)
        assert report.suggested_template == "knowledge-light"
        assert any(i.code == "no_executable_tree" for i in report.items)

    def test_warns_when_code_tree_missing_dev_test_command(self, projects_dir):
        ws = projects_dir / "app_no_dev"
        ws.mkdir()
        (ws / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (ws / "project.yaml").write_text(
            yaml.safe_dump(
                {"name": "无dev", "type": "software", "tools": ["read_file"]},
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        report = run_preflight(ws, projects_dir=projects_dir)
        assert any(i.code == "dev_test_command_missing" for i in report.items)

    def test_ok_when_dev_test_command_present(self, projects_dir):
        ws = projects_dir / "app_dev"
        ws.mkdir()
        (ws / "pyproject.toml").write_text("[project]\nname='x'\n", encoding="utf-8")
        (ws / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "有dev",
                    "type": "software",
                    "tools": ["read_file"],
                    "dev": {"test_command": "python3 -m pytest -q"},
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        report = run_preflight(ws, projects_dir=projects_dir)
        assert any(i.code == "dev_test_command" for i in report.items)
