"""Tests for terminal OS sandbox (bubblewrap wrapper)."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from butler.tools.terminal_sandbox import (
    SandboxFailure,
    classify_sandbox_failure,
    format_sandbox_error_payload,
    load_terminal_sandbox_config,
    should_run_sandboxed,
    wrap_argv_with_bubblewrap,
)


def test_load_sandbox_config_merges_repo_over_user(tmp_path, monkeypatch):
    user_dir = tmp_path / "user_butler"
    user_dir.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / ".butler").mkdir()
    (user_dir / "sandbox.json").write_text(
        json.dumps({"networkPolicy": {"default": "allow"}}),
        encoding="utf-8",
    )
    (repo / ".butler" / "sandbox.json").write_text(
        json.dumps({"networkPolicy": {"default": "deny", "allow": ["pypi.org"]}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_HOME", str(user_dir))
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "1")

    cfg = load_terminal_sandbox_config(repo)
    assert cfg.enabled is True
    assert cfg.network.default == "deny"
    assert "pypi.org" in cfg.network.allow


def test_should_run_sandboxed_respects_unsandboxed_approval():
    from butler.tools.terminal_sandbox import TerminalSandboxConfig

    cfg = TerminalSandboxConfig(enabled=True)
    assert should_run_sandboxed(cfg, unsandboxed_approved=False) is True
    assert should_run_sandboxed(cfg, unsandboxed_approved=True) is False


def test_wrap_argv_with_bubblewrap_structure(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    from butler.tools.terminal_sandbox import TerminalSandboxConfig

    cfg = TerminalSandboxConfig(enabled=True, sandbox_type="workspace_readwrite")
    with patch("butler.tools.terminal_sandbox.bubblewrap_path", return_value="/usr/bin/bwrap"):
        argv = wrap_argv_with_bubblewrap(["ls", "-la"], workspace=ws, config=cfg)
    assert argv[0] == "/usr/bin/bwrap"
    assert "--unshare-net" in argv
    assert "--bind" in argv
    assert argv[-2:] == ["ls", "-la"]


def test_classify_sandbox_network_failure():
    failure = classify_sandbox_failure(
        exit_code=1,
        stdout="",
        stderr="curl: (7) Couldn't connect to server — network blocked",
        sandboxed=True,
    )
    assert failure is not None
    assert failure.constraint == "network"
    assert failure.code == "SANDBOX_NETWORK_DENIED"


def test_format_sandbox_error_payload_includes_escalate():
    failure = SandboxFailure(constraint="network", code="SANDBOX_NETWORK_DENIED", message="blocked")
    payload = format_sandbox_error_payload(
        failure,
        command="curl https://example.com",
        exit_code=7,
        output="err",
    )
    assert payload["sandbox_constraint"] == "network"
    assert "/批准沙箱外" in payload["escalate_hint"]


def test_terminal_tool_uses_bwrap_when_enabled(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from unittest.mock import MagicMock

    from butler.execution_context import use_execution_context

    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "1")
    ws = tmp_path / "workspace"
    ws.mkdir()
    orch = MagicMock()
    orch.project_manager.get_current.return_value = SimpleNamespace(workspace=ws)

    captured: dict[str, object] = {}

    def fake_popen(argv, **kwargs):
        captured["argv"] = list(argv)
        captured["env"] = dict(kwargs.get("env") or {})
        proc = MagicMock()
        proc.stdout = MagicMock(fileno=lambda: -1)
        proc.stderr = MagicMock(fileno=lambda: -1)
        proc.poll.return_value = 0
        proc.returncode = 0
        proc.communicate.return_value = (b"ok\n", b"")
        proc.args = argv
        proc.kill = MagicMock()
        proc.wait = MagicMock()
        return proc

    with use_execution_context(orch, session_key="s1"):
        with patch("butler.tools.terminal_impl._is_selectable_pipe", return_value=False):
            with patch("subprocess.Popen", side_effect=fake_popen):
                with patch("butler.tools.terminal_sandbox.bubblewrap_path", return_value="/usr/bin/bwrap"):
                    from butler.tools.terminal_impl import _tool_terminal

                    raw = _tool_terminal("pwd", timeout=5, workdir=str(ws))
    data = json.loads(raw)
    assert data.get("exit_code") == 0
    argv = captured.get("argv")
    assert isinstance(argv, list)
    assert argv[0] == "/usr/bin/bwrap"
    assert captured["env"].get("BUTLER_SANDBOX") == "1"
