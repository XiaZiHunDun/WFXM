"""Deferred external-reference items implemented after phase C."""

from __future__ import annotations

import pytest

from butler.config_secrets import provider_secrets, write_provider_secret
from butler.core.tool_output_prune import clear_at_least_chars, prune_minimum_chars
from butler.tools.terminal_danger import check_dangerous_command
from butler.tools.terminal_pattern_approval import (
    approve_pattern,
    is_pattern_approved,
)


@pytest.mark.unit
def test_rm_rf_pattern_matches():
    r = check_dangerous_command("rm -rf /")
    assert not r.allowed
    assert r.pattern == "rm_rf"


@pytest.mark.unit
def test_terminal_pattern_approval_session():
    sk = "wx:pattern-test"
    assert not is_pattern_approved(sk, "rm_rf")
    approve_pattern(sk, "rm_rf")
    assert is_pattern_approved(sk, "rm_rf")
    from butler.tools.terminal_danger import set_terminal_session_context

    set_terminal_session_context(sk)
    r = check_dangerous_command("rm -rf /tmp/")
    assert r.allowed


@pytest.mark.unit
def test_clear_at_least_defaults_to_minimum(monkeypatch):
    monkeypatch.delenv("BUTLER_TOOL_PRUNE_CLEAR_AT_LEAST", raising=False)
    assert clear_at_least_chars() == prune_minimum_chars()


@pytest.mark.unit
def test_secrets_yaml_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    write_provider_secret("minimax", "sk-test-key", home=tmp_path)
    secrets = provider_secrets(tmp_path)
    assert secrets.get("minimax") == "sk-test-key"
