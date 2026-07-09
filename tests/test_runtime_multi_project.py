"""Multi-project runtime discovery."""

from pathlib import Path

import pytest

from butler.config import reload_butler_settings
from butler.project.manager import ProjectManager
from butler.runtime.service import discover_runtime_projects


@pytest.fixture
def repo_projects(monkeypatch):
    root = Path(__file__).resolve().parents[1]
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(root / "projects"))
    ProjectManager._instance = None  # type: ignore[misc]
    reload_butler_settings()
    yield
    ProjectManager._instance = None  # type: ignore[misc]
    reload_butler_settings()


def test_discover_includes_lingwen_and_demo(repo_projects):
    names = discover_runtime_projects()
    assert "灵文1号" in names
    assert "普通试点项目" in names
