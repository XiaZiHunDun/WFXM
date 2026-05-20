"""Gateway platform routing (native WeChat vs Hermes subprocess)."""

from __future__ import annotations

import pytest

from butler.gateway.platform_policy import (
    format_mixed_platform_error,
    normalize_platforms,
    partition_platforms,
    resolve_gateway_route,
)


@pytest.mark.unit
class TestNormalizePlatforms:
    def test_default_wechat(self):
        assert normalize_platforms("") == ["wechat"]

    def test_weixin_alias(self):
        assert normalize_platforms("weixin") == ["wechat"]

    def test_telegram_passthrough(self):
        assert normalize_platforms("telegram") == ["telegram"]


@pytest.mark.unit
class TestResolveGatewayRoute:
    def test_wechat_native(self):
        assert resolve_gateway_route(["wechat"]) == "native"

    def test_telegram_hermes(self):
        assert resolve_gateway_route(["telegram"]) == "hermes"

    def test_mixed_error(self):
        assert resolve_gateway_route(["wechat", "telegram"]) == "mixed_error"

    def test_mixed_error_message(self):
        msg = format_mixed_platform_error(["wechat", "slack"])
        assert "wechat" in msg
        assert "slack" in msg


@pytest.mark.unit
class TestPartitionPlatforms:
    def test_partition(self):
        native, hermes = partition_platforms(["wechat", "telegram", "discord"])
        assert native == ["wechat"]
        assert hermes == ["telegram", "discord"]
