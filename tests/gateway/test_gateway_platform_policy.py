"""WeChat-only gateway platform policy."""

from __future__ import annotations

import pytest

from butler.gateway.platform_policy import (
    format_unsupported_error,
    normalize_platforms,
    unsupported_platforms,
)


@pytest.mark.unit
class TestNormalizePlatforms:
    def test_default_wechat(self):
        assert normalize_platforms("") == ["wechat"]

    def test_weixin_alias(self):
        assert normalize_platforms("weixin") == ["wechat"]


@pytest.mark.unit
class TestUnsupportedPlatforms:
    def test_wechat_supported(self):
        assert unsupported_platforms(["wechat"]) == []

    def test_telegram_rejected(self):
        assert unsupported_platforms(["telegram"]) == ["telegram"]

    def test_error_message(self):
        msg = format_unsupported_error(["telegram", "slack"])
        assert "仅支持微信" in msg
        assert "telegram" in msg
