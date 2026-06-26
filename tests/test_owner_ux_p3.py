"""PROD-P3 Owner UX unit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from butler.core.task_route_hints import detect_cc_route_banner, score_heavy_coding_intent
from butler.gateway.gate_reply_templates import (
    workflow_gate_confirmed_hint,
    workflow_gate_pending_hint,
)
from butler.project.manager import ProjectManager


def _reset_pm() -> None:
    ProjectManager._instance = None


def _write_project(projects_dir: Path, folder: str, *, name: str) -> None:
    proj_dir = projects_dir / folder
    proj_dir.mkdir(parents=True)
    (proj_dir / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": name,
                "type": "content",
                "workspace": str(proj_dir),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )


@pytest.mark.unit
def test_switch_by_workspace_slug(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(root))
    _reset_pm()
    _write_project(root, "LingWen1", name="灵文1号")
    pm = ProjectManager()
    assert pm.resolve_project_name("LingWen1") == "灵文1号"
    assert pm.switch_project("lingwen1") is True
    assert pm.current_project == "灵文1号"


@pytest.mark.unit
def test_suggest_project_names_slug(tmp_path, monkeypatch):
    root = tmp_path / "projects"
    root.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(root))
    _reset_pm()
    _write_project(root, "LingWen1", name="灵文1号")
    pm = ProjectManager()
    hints = pm.suggest_project_names("LingWen1", limit=2)
    assert hints == ["灵文1号"]


@pytest.mark.unit
def test_workflow_gate_templates_auto_resume(monkeypatch):
    monkeypatch.setenv("BUTLER_WORKFLOW_AUTO_RESUME", "1")
    pending = workflow_gate_pending_hint(workflow="novel-factory", step_id="write")
    assert "自动续跑" in pending
    confirmed = workflow_gate_confirmed_hint(
        workflow="novel-factory", auto_resumed=True, step_id="write"
    )
    assert "自动续跑" in confirmed


@pytest.mark.unit
def test_cc_route_banner_heavy_refactor():
    assert score_heavy_coding_intent("请把整个代码库重构一遍") >= 4
    banner = detect_cc_route_banner("请把整个代码库重构一遍")
    assert banner is not None
    assert "CC" in banner or "本机" in banner


@pytest.mark.unit
def test_cc_route_skips_small_fix():
    assert detect_cc_route_banner("修一个 typo") is None
