"""R3-2: LLM tool writes to hooks.yaml are blocked (untrusted-config → RCE)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from butler.execution_context import use_execution_context
from butler.tools.path_safety import check_tool_path


def _orchestrator_for_workspace(workspace: Path):
    orch = MagicMock()  # noqa: magicmock-no-spec
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=workspace)
    return orch


def _orchestrator_without_project():
    orch = MagicMock()  # noqa: magicmock-no-spec
    orch.project_manager.get_current.return_value = None
    return orch


def test_write_project_hooks_yaml_denied(tmp_path):
    workspace = tmp_path / "proj"
    workspace.mkdir()
    (workspace / ".butler").mkdir()
    orch = _orchestrator_for_workspace(workspace)

    with use_execution_context(orch):
        result = check_tool_path(".butler/hooks.yaml", for_write=True)

    assert result.allowed is False
    assert "hooks configuration" in result.error


def test_write_project_plan_still_allowed(tmp_path):
    workspace = tmp_path / "proj"
    plan_dir = workspace / ".butler" / "plan"
    plan_dir.mkdir(parents=True)
    orch = _orchestrator_for_workspace(workspace)

    with use_execution_context(orch):
        result = check_tool_path(".butler/plan/step1.md", for_write=True)

    assert result.allowed is True


def test_write_global_hooks_denied(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    target = tmp_path / ".butler" / "hooks.yaml"

    with use_execution_context(_orchestrator_without_project()):
        result = check_tool_path(str(target), for_write=True)

    assert result.allowed is False
    assert "hooks configuration" in result.error
