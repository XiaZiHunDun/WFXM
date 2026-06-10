"""R3-3: hook subprocess env must not inherit full os.environ."""

from __future__ import annotations

from unittest import mock

from butler.hooks.runner import _run_hook
from butler.hooks.loader import HookRule


def test_run_hook_uses_sanitized_env(monkeypatch):
    monkeypatch.setenv("LD_PRELOAD", "/tmp/evil.so")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret-key")
    monkeypatch.setenv("PYTHONPATH", "/tmp/evil")

    captured: dict = {}

    def fake_run(cmd, **kwargs):
        captured["env"] = dict(kwargs.get("env") or {})
        proc = mock.Mock()
        proc.returncode = 0
        proc.stdout = "ok"
        proc.stderr = ""
        return proc

    rule = HookRule(
        event="PreToolUse",
        matcher="*",
        command="echo ok",
        cwd="/tmp",
    )
    payload = {"hook_event_name": "PreToolUse", "tool_name": "read_file"}

    with mock.patch("butler.hooks.runner.subprocess.run", side_effect=fake_run):
        code, out, err = _run_hook(rule, payload)

    assert code == 0
    env = captured["env"]
    assert "LD_PRELOAD" not in env
    assert "ANTHROPIC_API_KEY" not in env
    assert "PYTHONPATH" not in env
    assert env.get("BUTLER_HOOK_EVENT") == "PreToolUse"
    assert env.get("BUTLER_HOOK_TOOL") == "read_file"
    assert "BUTLER_HOOK_INPUT" in env
    assert env["PATH"] == "/usr/bin:/bin"
