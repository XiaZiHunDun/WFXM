"""Project policy: no default bind, environment tool scope, delete maturity gate."""

from __future__ import annotations

import json
from pathlib import Path

import pytest


def _reset_projects(monkeypatch, tmp_path: Path, *, projects_subdir: str = "projects") -> Path:
    projects_dir = tmp_path / projects_subdir
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    from butler.config import reload_butler_settings
    from butler.project.manager import ProjectManager

    ProjectManager._instance = None
    reload_butler_settings()
    return projects_dir


@pytest.mark.unit
def test_no_auto_default_project_without_bind(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_BIND_DEFAULT_PROJECT", "0")
    monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "Demo")
    projects_dir = _reset_projects(monkeypatch, tmp_path)
    ws = projects_dir / "Demo"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_text(
        "name: Demo\ntype: software\nstatus: active\n",
        encoding="utf-8",
    )
    from butler.project.manager import ProjectManager

    ProjectManager._instance = None
    pm = ProjectManager()
    assert pm.current_project == ""
    assert pm.resolve_active_project_name() == ""


@pytest.mark.unit
def test_bind_default_project_when_opt_in(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_BIND_DEFAULT_PROJECT", "1")
    monkeypatch.setenv("BUTLER_DEFAULT_PROJECT", "Demo")
    projects_dir = _reset_projects(monkeypatch, tmp_path)
    ws = projects_dir / "Demo"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_text(
        "name: Demo\ntype: software\nstatus: active\n",
        encoding="utf-8",
    )
    from butler.project.manager import ProjectManager

    ProjectManager._instance = None
    pm = ProjectManager()
    assert pm.current_project == "Demo"


@pytest.mark.unit
def test_environment_tool_root_uses_safe_root(monkeypatch, tmp_path):
    root = tmp_path / "env-root"
    root.mkdir()
    monkeypatch.setenv("BUTLER_TOOL_SCOPE", "environment")
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(root))
    from butler.tools.path_safety import tool_safe_root

    assert tool_safe_root() == root.resolve()


@pytest.mark.unit
def test_delete_maturity_gate_blocks_until_thresholds(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_PROJECT_DELETE_MATURITY_GATE", "1")
    monkeypatch.setenv("BUTLER_PROJECT_DELETE_MIN_LINES", "100")
    monkeypatch.setenv("BUTLER_PROJECT_DELETE_MIN_DEV_DELEGATES", "5")
    projects_dir = _reset_projects(monkeypatch, tmp_path)
    ws = projects_dir / "P1"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_text(
        "name: P1\ntype: software\nstatus: active\n",
        encoding="utf-8",
    )
    target = ws / "docs" / "drop-me.txt"
    target.parent.mkdir(parents=True)
    target.write_text("x", encoding="utf-8")

    from butler.project.manager import ProjectManager
    from butler.project.maturity import (
        delete_allowed_for_path,
        load_project_maturity,
        record_dev_delegate_run,
        record_lines_modified,
    )

    ProjectManager._instance = None
    assert not delete_allowed_for_path(target.resolve())[0]

    record_lines_modified("P1", 100)
    assert not delete_allowed_for_path(target.resolve())[0]
    for _ in range(5):
        record_dev_delegate_run("P1")
    assert delete_allowed_for_path(target.resolve())[0]
    stats = load_project_maturity("P1")
    assert stats.lines_modified_total >= 100
    assert stats.dev_delegate_runs >= 5


@pytest.mark.unit
def test_delete_file_tool_returns_maturity_error(monkeypatch, tmp_path):
    monkeypatch.setenv("BUTLER_TOOL_SCOPE", "environment")
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
    monkeypatch.setenv("BUTLER_PROJECT_DELETE_MATURITY_GATE", "1")
    monkeypatch.setenv("BUTLER_PROJECT_DELETE_MIN_LINES", "999999")
    projects_dir = _reset_projects(monkeypatch, tmp_path)
    ws = projects_dir / "P1"
    ws.mkdir(parents=True)
    (ws / "project.yaml").write_text(
        "name: P1\ntype: software\nstatus: active\n",
        encoding="utf-8",
    )
    rel = ws / "docs" / "x.txt"
    rel.parent.mkdir(parents=True)
    rel.write_text("hi", encoding="utf-8")

    from butler.project.manager import ProjectManager
    from butler.tools.file_io import _tool_delete_file

    ProjectManager._instance = None
    out = json.loads(_tool_delete_file(str(rel)))
    assert out.get("code") == "DELETE_MATURITY_GATE"
    assert rel.is_file()


@pytest.mark.unit
def test_personal_butler_unrestricted_tools(monkeypatch):
    from butler.tools.project_tools import allowed_tool_names_for_project

    allowed = allowed_tool_names_for_project(None, role="butler")
    assert allowed is None


@pytest.mark.unit
def test_lead_role_keeps_read_only_allowlist():
    from butler.tools.project_tools import allowed_tool_names_for_project

    allowed = allowed_tool_names_for_project(None, role="lead")
    assert allowed is not None
    assert "read_file" in allowed
    assert "terminal" not in allowed
    assert "write_file" not in allowed


@pytest.mark.unit
def test_wechat_minimal_filters_without_butler_role():
    from butler.execution_context import use_loop_role
    from butler.tools.toolset_profiles import TOOLSET_WECHAT_MINIMAL, filter_definitions_by_toolset

    defs = [
        {"type": "function", "function": {"name": n, "parameters": {}}}
        for n in ("read_file", "terminal", "run_workflow", "delete_file")
    ]
    with use_loop_role("lead"):
        names = {d["function"]["name"] for d in filter_definitions_by_toolset(defs, toolset=TOOLSET_WECHAT_MINIMAL)}
    assert "terminal" in names
    assert "run_workflow" in names
    assert "delete_file" not in names


@pytest.mark.unit
def test_wechat_minimal_bypassed_for_butler_role():
    from butler.execution_context import use_loop_role
    from butler.tools.toolset_profiles import TOOLSET_WECHAT_MINIMAL, filter_definitions_by_toolset

    defs = [
        {"type": "function", "function": {"name": n, "parameters": {}}}
        for n in ("read_file", "terminal", "delete_file")
    ]
    with use_loop_role("butler"):
        names = {d["function"]["name"] for d in filter_definitions_by_toolset(defs, toolset=TOOLSET_WECHAT_MINIMAL)}
    assert names == {"read_file", "terminal", "delete_file"}
