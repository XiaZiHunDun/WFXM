"""Tests for deploy profile diagnostics (PROD-P0-02)."""

from __future__ import annotations

import pytest

from butler.ops.deploy_profile import (
    effective_operating_profile,
    format_owner_profile_lines,
    profile_deviation_warnings,
)


@pytest.mark.unit
def test_effective_profile_dev_local(monkeypatch):
    monkeypatch.setenv("BUTLER_ENV_PROFILE", "dev-local")
    monkeypatch.setenv("BUTLER_DEPLOY_PROFILE", "dev")
    assert effective_operating_profile() == "dev-local"


@pytest.mark.unit
def test_effective_profile_dev_remote(monkeypatch):
    monkeypatch.setenv("BUTLER_ENV_PROFILE", "dev-remote")
    assert effective_operating_profile() == "dev-remote"


@pytest.mark.unit
def test_format_owner_profile_gateway_lines(monkeypatch):
    monkeypatch.setenv("BUTLER_DEPLOY_PROFILE", "gateway")
    monkeypatch.setenv("MINIMAX_API_KEY", "sk-test")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "wxid_test")
    lines = format_owner_profile_lines()
    text = "\n".join(lines)
    assert "gateway" in text
    assert "LLM Key" in text
    assert len(lines) <= 8


@pytest.mark.unit
def test_profile_warns_missing_owner_on_gateway(monkeypatch):
    monkeypatch.setenv("BUTLER_DEPLOY_PROFILE", "gateway")
    monkeypatch.setenv("BUTLER_ENV_PROFILE", "")
    monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    warns = profile_deviation_warnings()
    assert any("BUTLER_OWNER_WECHAT_ID" in w for w in warns)
