"""Tests for .butlerignore handling."""

from __future__ import annotations

from pathlib import Path

from butler.tools.butlerignore import (
    is_butlerignored,
    is_protected_write_path,
    load_ignore_patterns,
    matches_ignore_pattern,
)


def test_matches_ignore_pattern_glob():
    assert matches_ignore_pattern("secrets/api.key", "*.key")
    assert matches_ignore_pattern("build/output.log", "**/*.log")


def test_load_ignore_patterns_from_workspace(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".butlerignore").write_text("secrets/\n*.pem\n", encoding="utf-8")
    patterns = load_ignore_patterns(ws)
    assert "secrets/" in patterns
    assert "*.pem" in patterns


def test_is_butlerignored_denies_read(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    secret = ws / "secrets" / "token.txt"
    secret.parent.mkdir()
    secret.write_text("x", encoding="utf-8")
    (ws / ".butlerignore").write_text("secrets/**\n", encoding="utf-8")
    assert is_butlerignored(secret, workspace=ws) is True


def test_protected_write_blocks_git_config(tmp_path):
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / ".git").mkdir()
    cfg = ws / ".git" / "config"
    cfg.write_text("[core]\n", encoding="utf-8")
    assert is_protected_write_path(cfg, workspace=ws) is True


def test_check_tool_path_respects_butlerignore(tmp_path):
    from butler.execution_context import use_execution_context
    from butler.tools.path_safety import check_tool_path
    from unittest.mock import MagicMock
    from types import SimpleNamespace

    ws = tmp_path / "workspace"
    ws.mkdir()
    secret = ws / "private.txt"
    secret.write_text("secret", encoding="utf-8")
    (ws / ".butlerignore").write_text("private.txt\n", encoding="utf-8")
    orch = MagicMock()
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=ws)

    with use_execution_context(orch, session_key="s1"):
        result = check_tool_path("private.txt")

    assert result.allowed is False
    assert "butlerignore" in result.error
