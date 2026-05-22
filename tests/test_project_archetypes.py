"""Tests for project archetypes and create/register."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.project import Project
from butler.project_archetypes import load_template, validate_slug
from butler.project_lead import is_lead_project
from butler.project_manager import ProjectManager


def _reset_pm() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


@pytest.fixture
def projects_dir(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(root))
    monkeypatch.delenv("BUTLER_LEAD_PROJECTS", raising=False)
    _reset_pm()
    yield root
    _reset_pm()


@pytest.mark.unit
class TestArchetypes:
    def test_validate_slug_rejects_cjk(self):
        ok, _ = validate_slug("灵文1号")
        assert not ok

    def test_load_template_has_patch(self):
        data = load_template("software-default")
        assert "patch" in data.get("tools", [])


@pytest.mark.unit
class TestCreateAndLeadYaml:
    def test_create_uses_template_tools(self, projects_dir):
        pm = ProjectManager()
        created = pm.create_project("MyApp", display_name="我的应用")
        assert created is not None
        assert (created.workspace / "project.yaml").is_file()
        assert (created.workspace / ".butler/memory/MEMORY.md").is_file()
        raw = yaml.safe_load((created.workspace / "project.yaml").read_text(encoding="utf-8"))
        assert "patch" in raw["tools"]

    def test_lead_from_yaml_pack_without_env(self, projects_dir, monkeypatch):
        monkeypatch.setenv("BUTLER_LEAD_PROJECTS", "")
        ws = projects_dir / "nf"
        ws.mkdir()
        (ws / "project.yaml").write_text(
            yaml.safe_dump(
                {
                    "name": "书厂",
                    "type": "content",
                    "pack": "novel-factory",
                    "lead": True,
                    "tools": ["read_file"],
                },
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
        pm = ProjectManager()
        proj = pm.get_project("书厂")
        assert proj is not None
        assert is_lead_project("书厂", project=proj)

    def test_create_writes_runtime_template(self, projects_dir):
        pm = ProjectManager()
        created = pm.create_project("RtApp", display_name="Rt应用")
        jobs = created.workspace / "runtime" / "jobs.yaml"
        assert jobs.is_file()
        raw = jobs.read_text(encoding="utf-8")
        assert "test-unit-smoke" in raw

    def test_register_writes_yaml(self, projects_dir):
        ext = projects_dir / "imported"
        ext.mkdir()
        (ext / "README.md").write_text("hi", encoding="utf-8")
        pm = ProjectManager()
        proj = pm.register_workspace(ext, display_name="导入项")
        assert proj.name == "导入项"
        assert (ext / "project.yaml").is_file()
