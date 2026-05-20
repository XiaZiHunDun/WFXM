"""Tests for Butler-native gateway runner."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.runner import (
    normalize_platforms,
    run_gateway_blocking,
    unsupported_platforms,
)


class TestNormalizePlatforms:
    def test_default_wechat(self):
        assert normalize_platforms("") == ["wechat"]

    def test_weixin_alias(self):
        assert normalize_platforms("weixin") == ["wechat"]

    def test_unsupported_detection(self):
        assert unsupported_platforms(["telegram"]) == ["telegram"]
        assert unsupported_platforms(["wechat"]) == []


class TestGatewayCommand:
    def test_cmd_gateway_native_wechat(self, monkeypatch):
        from butler.main import _cmd_gateway

        ns = MagicMock(platforms="wechat", hermes_remainder=[])
        with patch("butler.gateway.runner.run_gateway_blocking", return_value=0) as run:
            assert _cmd_gateway(ns) == 0
        run.assert_called_once_with(["wechat"])

    def test_cmd_gateway_hermes_fallback_flag(self, monkeypatch):
        from butler.main import _cmd_gateway

        ns = MagicMock(platforms="telegram", hermes_remainder=["--hermes-fallback"])
        with patch("butler.main._cmd_gateway_hermes_fallback", return_value=5) as fallback:
            assert _cmd_gateway(ns) == 5
        fallback.assert_called_once()

    def test_cmd_gateway_rejects_unsupported_without_fallback(self, monkeypatch, capsys):
        from butler.main import _cmd_gateway

        ns = MagicMock(platforms="telegram", hermes_remainder=[])
        assert _cmd_gateway(ns) == 2
        assert "hermes-fallback" in capsys.readouterr().err


@pytest.mark.module_test
class TestWeChatAdapterWiring:
    def test_butler_handler_wrapper(self):
        from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource
        from butler.gateway.runner import _butler_message_handler

        butler = MagicMock()
        butler.handle_message.return_value = "ok"
        event = MessageEvent(
            text="你好",
            message_type=MessageType.TEXT,
            source=SessionSource(platform="wechat", chat_id="u1", user_id="u1"),
        )
        import asyncio
        out = asyncio.run(_butler_message_handler(butler, event))
        assert out == "ok"
        butler.handle_message.assert_called_once()
        assert butler.handle_message.call_args.kwargs["platform"] == "wechat"
