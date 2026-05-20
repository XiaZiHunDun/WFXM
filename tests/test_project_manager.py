"""Unit tests for butler.project_manager.ProjectManager."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project_manager import ProjectManager


def _reset_pm() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _write_project(projects_dir: Path, folder: str, *, name: str, description: str = "") -> None:
    proj_dir = projects_dir / folder
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "type": "content",
                "description": description or f"{name} project",
                "workspace": str(proj_dir),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(root))
    _reset_pm()
    yield root
    _reset_pm()


@pytest.mark.unit
class TestProjectManagerSwitch:
    def test_switch_exact_display_name(self, projects_dir):
        _write_project(projects_dir, "LingWen", name="灵文", description="小说工厂")
        pm = ProjectManager()
        assert pm.switch_project("灵文") is True
        assert pm.current_project == "灵文"
        assert pm.get_current() is not None
        assert pm.get_current().name == "灵文"

    def test_switch_fuzzy_substring(self, projects_dir):
        _write_project(projects_dir, "LingWen", name="灵文", description="小说工厂")
        pm = ProjectManager()
        assert pm.switch_project("灵") is True
        assert pm.current_project == "灵文"

    def test_switch_case_insensitive_substring(self, projects_dir):
        _write_project(projects_dir, "demo", name="DemoProject")
        pm = ProjectManager()
        assert pm.switch_project("demo") is True
        assert pm.current_project == "DemoProject"

    def test_switch_unknown_returns_false(self, projects_dir):
        _write_project(projects_dir, "only", name="only")
        pm = ProjectManager()
        assert pm.switch_project("missing") is False
        assert pm.current_project == ""
