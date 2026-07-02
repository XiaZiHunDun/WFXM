"""Tests for terminal env profiles."""

from __future__ import annotations

import importlib.util
from pathlib import Path


from butler.ops.env_profiles import profile_expectation, profile_mismatch_messages


def test_dev_local_expects_no_sandbox():
    exp = profile_expectation("dev-local")
    assert exp is not None
    assert exp.terminal_enabled is True
    assert exp.sandbox_enabled is False


def test_profile_mismatch_when_sandbox_on_for_dev_local(monkeypatch):
    monkeypatch.setenv("BUTLER_ENV_PROFILE", "dev-local")
    monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX", "1")
    monkeypatch.setenv("BUTLER_TERMINAL_SANDBOX_FAIL_UNAVAILABLE", "0")
    msgs = profile_mismatch_messages(bwrap_available=False)
    assert any("BUTLER_TERMINAL_SANDBOX=0" in m for m in msgs)


def test_apply_profile_script_dev_local(tmp_path):
    env = tmp_path / ".env"
    env.write_text("FOO=bar\nBUTLER_ENABLE_TERMINAL=1\nBUTLER_TERMINAL_SANDBOX=1\n", encoding="utf-8")
    script = Path(__file__).resolve().parents[1] / "scripts" / "apply-butler-env-profile.py"
    spec = importlib.util.spec_from_file_location("apply_butler_env_profile", script)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(mod)
    mod.apply_profile(env, "dev-local")
    text = env.read_text(encoding="utf-8")
    assert "BUTLER_ENV_PROFILE=dev-local" in text
    assert "BUTLER_TERMINAL_SANDBOX=0" in text
    assert "BUTLER_TOOLSET=full" in text
    assert "BUTLER_SKILL_WRITE_APPROVAL=0" in text
    assert "FOO=bar" in text
    assert "BUTLER_TERMINAL_SANDBOX=1" not in text
