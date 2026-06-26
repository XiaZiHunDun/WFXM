"""Tests for ``butler onboard`` (PROD-P6-01)."""

from __future__ import annotations

from butler.ops.onboard import format_onboard_report, resolve_onboard_profile


def test_onboard_gateway_report_sections():
    text = format_onboard_report(profile="gateway")
    assert "Butler 上手一页纸" in text
    assert "剖面：gateway" in text
    assert "必填项" in text
    assert "BUTLER_OWNER_WECHAT_ID" in text
    assert "wechat-setup" in text
    assert "deploy-profiles" in text


def test_onboard_dev_local_next_steps():
    text = format_onboard_report(profile="dev-local")
    assert "butler-pytest-fast-gate" in text
    assert "BUTLER_DEPLOY_PROFILE" in text


def test_resolve_onboard_profile_explicit():
    assert resolve_onboard_profile("dev-remote") == "dev-remote"
