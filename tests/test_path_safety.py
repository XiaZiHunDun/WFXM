from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from butler.execution_context import use_execution_context
from butler.tools.path_safety import (
    check_tool_path,
    current_workspace_root,
    safe_subprocess_env,
)


def _orchestrator_for_workspace(workspace: Path):
    orch = MagicMock()  # noqa: magicmock-no-spec — path safety facade (orch)
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=workspace)
    return orch


def _orchestrator_without_project():
    orch = MagicMock()  # noqa: magicmock-no-spec — path safety facade (orch)
    orch.project_manager.get_current.return_value = None
    return orch


def test_current_workspace_root_uses_execution_context_project(tmp_path):
    orch = _orchestrator_for_workspace(tmp_path)

    with use_execution_context(orch, session_key="s1"):
        assert current_workspace_root() == tmp_path.resolve()


def test_relative_path_resolves_inside_workspace(tmp_path):
    orch = _orchestrator_for_workspace(tmp_path)

    with use_execution_context(orch):
        result = check_tool_path("src/app.py")

    assert result.allowed is True
    assert result.path == (tmp_path / "src/app.py").resolve()


def test_path_outside_workspace_is_denied(tmp_path):
    workspace = tmp_path / "workspace"
    outside = tmp_path / "outside.txt"
    workspace.mkdir()
    outside.write_text("secret", encoding="utf-8")
    orch = _orchestrator_for_workspace(workspace)

    with use_execution_context(orch):
        result = check_tool_path(str(outside))

    assert result.allowed is False
    assert "outside workspace" in result.error


def test_context_without_project_denies_tool_paths(tmp_path):
    target = tmp_path / "file.txt"
    target.write_text("content", encoding="utf-8")

    with use_execution_context(_orchestrator_without_project()):
        result = check_tool_path(str(target))

    assert result.allowed is False
    assert "outside workspace" in result.error


def test_sensitive_paths_are_denied_without_workspace():
    result = check_tool_path("~/.ssh/id_ed25519")

    assert result.allowed is False
    assert "sensitive" in result.error


def test_sensitive_paths_are_denied_for_write_without_workspace():
    result = check_tool_path("~/.ssh/config", for_write=True)

    assert result.allowed is False
    assert "sensitive" in result.error


def test_hardlinked_files_are_denied(tmp_path):
    original = tmp_path / "original.txt"
    hardlink = tmp_path / "hardlink.txt"
    original.write_text("shared", encoding="utf-8")
    try:
        hardlink.hardlink_to(original)
    except OSError:
        pytest.skip("hardlinks are not supported on this filesystem")

    orch = _orchestrator_for_workspace(tmp_path)
    with use_execution_context(orch):
        result = check_tool_path(str(hardlink))

    assert result.allowed is False
    assert "hardlinked" in result.error


def test_safe_subprocess_env_drops_loader_and_tool_config(monkeypatch):
    monkeypatch.setenv("LD_PRELOAD", "/tmp/evil.so")
    monkeypatch.setenv("DYLD_INSERT_LIBRARIES", "/tmp/evil.dylib")
    monkeypatch.setenv("RIPGREP_CONFIG_PATH", "/tmp/evil-rg-config")
    monkeypatch.setenv("PYTHONPATH", "/tmp/evil-pythonpath")

    env = safe_subprocess_env()

    assert env["PATH"] == "/usr/bin:/bin"
    assert "LD_PRELOAD" not in env
    assert "DYLD_INSERT_LIBRARIES" not in env
    assert "RIPGREP_CONFIG_PATH" not in env
    assert "PYTHONPATH" not in env
