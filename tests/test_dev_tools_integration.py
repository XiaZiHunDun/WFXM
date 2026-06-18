"""End-to-end dev tools smoke in an isolated git workspace."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from butler.tools.registry import dispatch_tool


@pytest.fixture(autouse=True)
def _dev_env(tmp_path, monkeypatch):
    ws = tmp_path / "workspace"
    ws.mkdir()
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(ws))
    monkeypatch.setattr(
        "butler.tools.path_safety.current_workspace_root",
        lambda: None,
    )
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_PROFILE", "dev")
    monkeypatch.setenv("BUTLER_ENABLE_GIT", "1")
    monkeypatch.setenv("BUTLER_ENABLE_GIT_WRITE", "1")
    subprocess.run(["git", "init"], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "smoke@test.local"],
        cwd=ws,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "Butler Smoke"],
        cwd=ws,
        check=True,
        capture_output=True,
    )
    (ws / "hello.py").write_text("def greet():\n    return 'hi'\n", encoding="utf-8")
    subprocess.run(["git", "add", "hello.py"], cwd=ws, check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=ws,
        check=True,
        capture_output=True,
    )
    return ws


@pytest.mark.module_test
def test_dev_workflow_patch_terminal_git(_dev_env):
    ws: Path = _dev_env

    patch_raw = dispatch_tool(
        "patch",
        {
            "path": str(ws / "hello.py"),
            "old_string": "return 'hi'",
            "new_string": "return 'hello'",
        },
    )
    patch_data = json.loads(patch_raw)
    assert patch_data.get("success") is True

    runner = ws / "_smoke_run.py"
    runner.write_text(
        "import hello\nassert hello.greet() == 'hello'\n",
        encoding="utf-8",
    )
    term_raw = dispatch_tool(
        "terminal",
        {
            "command": f"python3 {runner.name}",
            "workdir": str(ws),
        },
    )
    term_data = json.loads(term_raw)
    assert term_data.get("exit_code") == 0, term_data

    status_raw = dispatch_tool("git_status", {"workdir": str(ws)})
    status_data = json.loads(status_raw)
    assert status_data.get("exit_code") == 0
    assert "hello.py" in status_data.get("stdout", "")

    add_raw = dispatch_tool(
        "git_add",
        {"files": ["hello.py"], "workdir": str(ws)},
    )
    assert json.loads(add_raw).get("exit_code") == 0

    commit_raw = dispatch_tool(
        "git_commit",
        {"message": "smoke: update greet", "workdir": str(ws)},
    )
    commit_data = json.loads(commit_raw)
    assert commit_data.get("exit_code") == 0

    log_raw = dispatch_tool("git_log", {"count": 3, "workdir": str(ws)})
    log_data = json.loads(log_raw)
    assert "smoke" in log_data.get("stdout", "")
