"""WeChat iLink account persistence (wechat-setup / gateway startup)."""

from __future__ import annotations

import json

import pytest

from butler.gateway.platforms.types import PlatformConfig
from butler.gateway.platforms.wechat_ilink import (
    WeChatAdapter,
    _account_file,
    load_wechat_account,
    save_wechat_account,
)


@pytest.mark.unit
class TestWechatAccountPersistence:
    def test_save_and_load_roundtrip(self, tmp_butler_home):
        home = str(tmp_butler_home)
        save_wechat_account(
            home,
            account_id="bot-persist-1",
            token="secret-token-xyz",
            base_url="https://ilinkai.weixin.qq.com",
            user_id="user-1",
        )
        path = _account_file(home, "bot-persist-1")
        assert path.exists()
        assert oct(path.stat().st_mode)[-3:] == "600"

        loaded = load_wechat_account(home, "bot-persist-1")
        assert loaded is not None
        assert loaded["token"] == "secret-token-xyz"
        assert loaded["base_url"] == "https://ilinkai.weixin.qq.com"
        assert loaded["user_id"] == "user-1"

    def test_load_missing_account_returns_none(self, tmp_butler_home):
        assert load_wechat_account(str(tmp_butler_home), "no-such-bot") is None


@pytest.mark.integration
class TestWechatAdapterLoadsPersistedToken:
    def test_init_loads_token_from_accounts_when_env_token_empty(
        self, tmp_butler_home, monkeypatch
    ):
        from butler.config import get_butler_home, reload_butler_settings

        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        monkeypatch.setenv("WECHAT_TOKEN", "")
        monkeypatch.setenv("WEIXIN_TOKEN", "")
        reload_butler_settings()
        home = str(get_butler_home())

        save_wechat_account(
            home,
            account_id="bot-load-1",
            token="from-disk-token",
            base_url="https://ilinkai.weixin.qq.com",
        )
        assert load_wechat_account(home, "bot-load-1")["token"] == "from-disk-token"

        adapter = WeChatAdapter(
            PlatformConfig(
                token="",
                extra={"account_id": "bot-load-1"},
            ),
        )
        assert adapter._token == "from-disk-token"
        assert adapter._account_id == "bot-load-1"

    def test_env_token_overrides_persisted_account(self, tmp_butler_home, monkeypatch):
        from butler.config import get_butler_home, reload_butler_settings

        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        monkeypatch.setenv("WECHAT_TOKEN", "from-env-token")
        reload_butler_settings()
        home = str(get_butler_home())

        save_wechat_account(
            home,
            account_id="bot-load-2",
            token="from-disk-token",
            base_url="https://ilinkai.weixin.qq.com",
        )

        adapter = WeChatAdapter(
            PlatformConfig(token="", extra={"account_id": "bot-load-2"}),
        )
        assert adapter._token == "from-env-token"
