"""R1-4 wechat_ilink.py god-module split — backward-compat guard.

Asserts the public API of the original ``wechat_ilink`` module still works
exactly as before, even after extraction of pure constants and pure
utility helpers into sibling modules.

New sibling modules:
- ``butler.gateway.platforms.wechat_ilink_constants`` (URLs / codes / enums)
- ``butler.gateway.platforms.wechat_ilink_utils`` (crypto / CDN / account / parsing)

Backward-compat: every previously-importable symbol must still be reachable
via ``butler.gateway.platforms.wechat_ilink`` (the adapter module).
"""

from __future__ import annotations

import importlib

import pytest


WECHAT_ILINK_PATH = "butler.gateway.platforms.wechat_ilink"
WECHAT_ILINK_CONSTANTS_PATH = "butler.gateway.platforms.wechat_ilink_constants"
WECHAT_ILINK_UTILS_PATH = "butler.gateway.platforms.wechat_ilink_utils"


@pytest.mark.unit
class TestSplitModulesExist:
    def test_constants_module_exists(self):
        mod = importlib.import_module(WECHAT_ILINK_CONSTANTS_PATH)
        assert mod is not None

    def test_utils_module_exists(self):
        mod = importlib.import_module(WECHAT_ILINK_UTILS_PATH)
        assert mod is not None


@pytest.mark.unit
class TestBackwardCompatSymbols:
    """Symbols that test files and other modules import from wechat_ilink.

    Re-exports must keep them reachable via the original import path so
    test patches and runtime imports stay green.
    """

    @pytest.mark.parametrize(
        "name",
        [
            "WeChatAdapter",
            "SESSION_EXPIRED_ERRCODE",
            "TYPING_START",
            "ITEM_IMAGE",
            "ITEM_TEXT",
            "ITEM_VOICE",
            "ITEM_FILE",
            "ITEM_VIDEO",
            "MEDIA_IMAGE",
            "MEDIA_VIDEO",
            "MEDIA_FILE",
            "MEDIA_VOICE",
            "MSG_TYPE_BOT",
            "MSG_STATE_FINISH",
            "TYPING_STOP",
            "ILINK_BASE_URL",
            "WECHAT_CDN_BASE_URL",
            "EP_GET_UPDATES",
            "EP_SEND_MESSAGE",
            "ContextTokenStore",
            "check_wechat_requirements",
            "qr_login",
            "send_wechat_direct",
        ],
    )
    def test_symbol_importable_from_wechat_ilink(self, name):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert hasattr(mod, name), f"{name} missing from {WECHAT_ILINK_PATH}"

    @pytest.mark.parametrize(
        "name",
        [
            "_extract_text",
            "_assert_wechat_cdn_url",
            "_download_and_decrypt_media",
            "_download_bytes",
            "_account_file",
            "load_wechat_account",
            "save_wechat_account",
            "_make_ssl_connector",
            "_safe_id",
            "_headers",
            "_random_wechat_uin",
        ],
    )
    def test_helper_importable_from_wechat_ilink(self, name):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert hasattr(mod, name), f"{name} missing from {WECHAT_ILINK_PATH}"


@pytest.mark.unit
class TestLiveAdaptersRegistryUntouched:
    """R1-12 owns ``_LIVE_ADAPTERS``; this test only locks in dict type.

    The audit says R1-12 will be addressed separately. For R1-4, we just
    ensure the global is still a module-level dict on the original
    import path.
    """

    def test_live_adapters_is_dict(self):
        mod = importlib.import_module(WECHAT_ILINK_PATH)
        assert isinstance(mod._LIVE_ADAPTERS, dict)


@pytest.mark.unit
class TestConstantsModuleContent:
    def test_ilink_base_url_value(self):
        from butler.gateway.platforms.wechat_ilink_constants import ILINK_BASE_URL

        assert ILINK_BASE_URL == "https://ilinkai.weixin.qq.com"

    def test_session_expired_errcode_value(self):
        from butler.gateway.platforms.wechat_ilink_constants import SESSION_EXPIRED_ERRCODE

        assert SESSION_EXPIRED_ERRCODE == -14

    def test_rate_limit_errcode_value(self):
        from butler.gateway.platforms.wechat_ilink_constants import RATE_LIMIT_ERRCODE

        assert RATE_LIMIT_ERRCODE == -2


@pytest.mark.unit
class TestUtilsModuleContent:
    def test_safe_id_truncates(self):
        from butler.gateway.platforms.wechat_ilink_utils import _safe_id

        assert _safe_id("") == "?"
        assert _safe_id("short") == "short"
        assert _safe_id("a-very-long-identifier-1234567890", keep=4) == "a-ve"

    def test_extract_text_plain(self):
        from butler.gateway.platforms.wechat_ilink_constants import ITEM_TEXT
        from butler.gateway.platforms.wechat_ilink_utils import _extract_text

        items = [{"type": ITEM_TEXT, "text_item": {"text": "hello"}}]
        assert _extract_text(items) == "hello"

    def test_assert_wechat_cdn_url_rejects_evil(self):
        from butler.gateway.platforms.wechat_ilink_utils import _assert_wechat_cdn_url

        with pytest.raises(ValueError, match="allowlist"):
            _assert_wechat_cdn_url("https://evil.example.com/x.jpg")

    def test_assert_wechat_cdn_url_accepts_official(self):
        from butler.gateway.platforms.wechat_ilink_utils import _assert_wechat_cdn_url

        _assert_wechat_cdn_url("https://novac2c.cdn.wechat.qq.com/c2c/abc")
