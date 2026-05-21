"""Git tools and terminal profile (dev ops)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from butler.tools.registry import dispatch_tool, get_tool_definitions
from butler.tools.path_safety import _allowed_terminal_commands


@pytest.fixture(autouse=True)
def _safe_root(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))


@pytest.mark.module_test
class TestGitToolsEnvGate:
    def test_git_disabled_by_default(self, tmp_path):
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        raw = dispatch_tool("git_status", {"workdir": str(repo)})
        data = json.loads(raw)
        assert "GIT_DISABLED" in str(data.get("code", "")) or "BUTLER_ENABLE_GIT" in str(
            data.get("error", "")
        )

    def test_git_status_when_enabled(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_GIT", "1")
        repo = tmp_path / "repo"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        (repo / "a.txt").write_text("hi\n", encoding="utf-8")
        raw = dispatch_tool("git_status", {"workdir": str(repo)})
        data = json.loads(raw)
        assert data.get("exit_code") == 0
        assert "a.txt" in data.get("stdout", "") or "??" in data.get("stdout", "")

    def test_git_write_blocked_without_flag(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_GIT", "1")
        repo = tmp_path / "repo2"
        repo.mkdir()
        subprocess.run(["git", "init"], cwd=repo, check=True, capture_output=True)
        raw = dispatch_tool("git_commit", {"message": "test", "workdir": str(repo)})
        data = json.loads(raw)
        assert "GIT_WRITE" in str(data.get("code", "")) or "GIT_WRITE" in str(
            data.get("error", "")
        )


@pytest.mark.module_test
class TestGitToolsRegistered:
    def test_git_tools_in_registry(self):
        names = {t["function"]["name"] for t in get_tool_definitions()}
        for name in (
            "git_status",
            "git_diff",
            "git_log",
            "git_branch",
            "git_add",
            "git_commit",
        ):
            assert name in names


@pytest.mark.module_test
class TestTerminalProfile:
    def test_dev_profile_includes_pytest(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TERMINAL_ALLOWLIST_EXTRA", raising=False)
        monkeypatch.setenv("BUTLER_TERMINAL_PROFILE", "dev")
        allowed = _allowed_terminal_commands()
        assert "pytest" in allowed
        assert "git" in allowed

    def test_pilot_profile(self, monkeypatch):
        monkeypatch.delenv("BUTLER_TERMINAL_ALLOWLIST_EXTRA", raising=False)
        monkeypatch.setenv("BUTLER_TERMINAL_PROFILE", "pilot")
        allowed = _allowed_terminal_commands()
        assert "python3" in allowed
        assert "pytest" not in allowed


@pytest.mark.module_test
class TestPatchMultiMatch:
    def test_patch_reports_match_lines(self, tmp_path):
        f = tmp_path / "dup.py"
        f.write_text("x = 1\nx = 2\n", encoding="utf-8")
        raw = dispatch_tool(
            "patch",
            {"path": str(f), "old_string": "x = ", "new_string": "y = "},
        )
        data = json.loads(raw)
        assert "found 2 times" in data.get("error", "")
        assert len(data.get("matches", [])) >= 2
