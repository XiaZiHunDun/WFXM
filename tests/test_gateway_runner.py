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

    def test_cmd_gateway_telegram_requires_hermes_vendored(self, monkeypatch, capsys):
        from butler.main import _cmd_gateway

        ns = MagicMock(platforms="telegram", hermes_remainder=[])
        with patch("butler.gateway.platform_policy.hermes_vendored_installed", return_value=False):
            assert _cmd_gateway(ns) == 2
        assert "hermes-gateway" in capsys.readouterr().err

    def test_cmd_gateway_telegram_auto_hermes_when_installed(self, monkeypatch):
        from butler.main import _cmd_gateway

        ns = MagicMock(platforms="telegram", hermes_remainder=[])
        with patch("butler.gateway.platform_policy.hermes_vendored_installed", return_value=True):
            with patch("butler.main._cmd_gateway_hermes_fallback", return_value=0) as fb:
                assert _cmd_gateway(ns) == 0
        fb.assert_called_once()


class TestPlatformAdapterStubs:
    def test_extract_media_returns_content(self):
        from butler.gateway.platforms.base import ButlerPlatformAdapter
        from butler.gateway.platforms.types import PlatformConfig

        class _Stub(ButlerPlatformAdapter):
            def __init__(self, config, platform: str) -> None:
                super().__init__(config, platform)
                self.typing_calls = 0
                self.stop_calls = 0

            async def connect(self) -> bool:
                return True

            async def disconnect(self) -> None:
                pass

            async def send(self, chat_id: str, content: str, reply_to=None, metadata=None):
                del chat_id, content, reply_to, metadata
                from butler.gateway.platforms.types import SendResult

                return SendResult(success=True)

            async def send_typing(self, chat_id: str, metadata=None) -> None:
                del chat_id, metadata
                self.typing_calls += 1

            async def stop_typing(self, chat_id: str) -> None:
                del chat_id
                self.stop_calls += 1

        adapter = _Stub(PlatformConfig(), "wechat")
        media, text = adapter.extract_media("你好 Butler")
        assert media == []
        assert text == "你好 Butler"

    def test_mark_connected_disconnected(self):
        from butler.gateway.platforms.base import ButlerPlatformAdapter
        from butler.gateway.platforms.types import PlatformConfig, SendResult

        class _Stub(ButlerPlatformAdapter):
            async def connect(self) -> bool:
                return True

            async def disconnect(self) -> None:
                self._mark_disconnected()

            async def send(self, chat_id: str, content: str, reply_to=None, metadata=None):
                del chat_id, content, reply_to, metadata
                return SendResult(success=True)

        adapter = _Stub(PlatformConfig(), "wechat")
        adapter._mark_connected()
        assert adapter.is_connected is True
        adapter._mark_disconnected()
        assert adapter.is_connected is False

    @pytest.mark.asyncio
    async def test_handle_message_invokes_typing_lifecycle(self, monkeypatch):
        from butler.gateway.platforms.base import ButlerPlatformAdapter
        from butler.gateway.platforms.types import MessageEvent, MessageType, PlatformConfig, SessionSource

        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "0")

        class _Stub(ButlerPlatformAdapter):
            def __init__(self, config, platform: str) -> None:
                super().__init__(config, platform)
                self.typing_calls = 0
                self.stop_calls = 0

            async def connect(self) -> bool:
                return True

            async def disconnect(self) -> None:
                pass

            async def send(self, chat_id: str, content: str, reply_to=None, metadata=None):
                del chat_id, content, reply_to, metadata
                from butler.gateway.platforms.types import SendResult

                return SendResult(success=True)

            async def send_typing(self, chat_id: str, metadata=None) -> None:
                del chat_id, metadata
                self.typing_calls += 1

            async def stop_typing(self, chat_id: str) -> None:
                del chat_id
                self.stop_calls += 1

        adapter = _Stub(PlatformConfig(), "wechat")

        async def _handler(event: MessageEvent) -> str:
            del event
            return "pong"

        adapter.set_message_handler(_handler)
        event = MessageEvent(
            text="ping",
            message_type=MessageType.TEXT,
            source=SessionSource(platform="wechat", chat_id="u1", user_id="u1"),
        )
        await adapter.handle_message(event)
        assert adapter.typing_calls >= 1
        assert adapter.stop_calls == 1


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
