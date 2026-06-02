"""Sprint 8 audit fix: SEC-3 — Owner 网关 fail-closed

Sprint 8 SEC-3：`butler/gateway/owner_gate.py:58-64` 默认 fail-open：
  - 非微信平台无条件放行
  - 微信平台 owner 列表空时无条件放行
应该默认 fail-closed，仅在 BUTLER_PROJECT_CREATE_OPEN=1 时放行。
"""

from __future__ import annotations

import pytest

from butler.gateway.owner_gate import is_gateway_owner, owner_wechat_ids


@pytest.mark.unit
class TestOwnerGateFailClosed:
    def test_non_wechat_denied_without_open_flag(self, monkeypatch):
        """非微信平台 + 未开 BUTLER_PROJECT_CREATE_OPEN → 必须拒绝。"""
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        assert not is_gateway_owner(platform="cli", external_id="anyone")
        assert not is_gateway_owner(platform="telegram", external_id="user_x")

    def test_empty_allowlist_denies_all(self, monkeypatch):
        """owner 列表空 → 必须拒绝任何人。"""
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
        assert owner_wechat_ids() == frozenset()
        assert not is_gateway_owner(platform="wechat", external_id="anyone")

    def test_open_env_still_bypasses(self, monkeypatch):
        """BUTLER_PROJECT_CREATE_OPEN=1 显式 opt-in 仍应放行。"""
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        assert is_gateway_owner(platform="cli", external_id="any")
        assert is_gateway_owner(platform="wechat", external_id="stranger")

    def test_wechat_allowlist_unchanged(self, monkeypatch):
        """正常路径：owner / friend 通过、stranger 拒绝 — 不回归。"""
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "friend2")
        assert is_gateway_owner(platform="wechat", external_id="owner1")
        assert is_gateway_owner(platform="wechat", external_id="friend2")
        assert not is_gateway_owner(platform="wechat", external_id="stranger")
