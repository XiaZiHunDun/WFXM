"""Owner gate for WeChat project create."""

from __future__ import annotations

import pytest

from butler.gateway.owner_gate import (
    is_gateway_owner,
    owner_wechat_ids,
    resolve_owner_wechat_chat_id,
)


@pytest.mark.unit
class TestOwnerGate:
    def test_open_env_bypasses(self, monkeypatch):
        monkeypatch.setenv("BUTLER_PROJECT_CREATE_OPEN", "1")
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        assert is_gateway_owner(platform="wechat", external_id="other")

    def test_wechat_allowlist(self, monkeypatch):
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "friend2")
        assert is_gateway_owner(platform="wechat", external_id="owner1")
        assert is_gateway_owner(platform="wechat", external_id="friend2")
        assert not is_gateway_owner(platform="wechat", external_id="stranger")

    def test_non_wechat_always_allowed(self, monkeypatch):
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        assert is_gateway_owner(platform="cli", external_id="any")

    def test_empty_allowlist_allows_all(self, monkeypatch):
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.delenv("BUTLER_GATEWAY_ALLOWLIST", raising=False)
        assert owner_wechat_ids() == frozenset()
        assert is_gateway_owner(platform="wechat", external_id="anyone")

    def test_gateway_allowlist_is_honored_for_owner_gate(self, monkeypatch):
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.delenv("BUTLER_OWNER_WECHAT_ID", raising=False)
        monkeypatch.delenv("WECHAT_ALLOWED_USERS", raising=False)
        monkeypatch.setenv("BUTLER_GATEWAY_ALLOWLIST", "legacy1,legacy2")

        assert owner_wechat_ids() == frozenset({"legacy1", "legacy2"})
        assert resolve_owner_wechat_chat_id() == "legacy1"
        assert is_gateway_owner(platform="wechat", external_id="legacy2")
        assert not is_gateway_owner(platform="wechat", external_id="stranger")

    def test_gateway_allowlist_is_fallback_only_for_owner_gate(self, monkeypatch):
        monkeypatch.delenv("BUTLER_PROJECT_CREATE_OPEN", raising=False)
        monkeypatch.setenv("BUTLER_OWNER_WECHAT_ID", "owner1")
        monkeypatch.setenv("WECHAT_ALLOWED_USERS", "friend2")
        monkeypatch.setenv("BUTLER_GATEWAY_ALLOWLIST", "legacy1,legacy2")

        assert owner_wechat_ids() == frozenset({"owner1", "friend2"})
        assert resolve_owner_wechat_chat_id() == "owner1"
        assert not is_gateway_owner(platform="wechat", external_id="legacy1")
