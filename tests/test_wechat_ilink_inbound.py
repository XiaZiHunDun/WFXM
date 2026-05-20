"""WeChat iLink inbound parsing (maps to transport layer smoke, no live HTTP)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from butler.gateway.platforms.types import MessageEvent, MessageType, PlatformConfig
from butler.gateway.platforms.wechat_ilink import (
    ITEM_IMAGE,
    ITEM_TEXT,
    WeChatAdapter,
    _extract_text,
)


@pytest.mark.unit
class TestExtractText:
    def test_plain_text_item(self):
        items = [{"type": ITEM_TEXT, "text_item": {"text": "你好 Butler"}}]
        assert _extract_text(items) == "你好 Butler"


@pytest.mark.integration
class TestInboundMessage:
    @pytest.mark.asyncio
    async def test_process_message_builds_event_and_stores_context_token(
        self, tmp_path, monkeypatch, tmp_butler_home
    ):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        def _fake_create_task(coro, *args, **kwargs):
            if asyncio.iscoroutine(coro):
                coro.close()
            return MagicMock()

        monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
        monkeypatch.setenv("BUTLER_GATEWAY_TYPING_ENABLED", "0")
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "0")

        adapter = WeChatAdapter(
            PlatformConfig(token="test-token", extra={"account_id": "bot-acc"}),
        )
        adapter._poll_session = MagicMock()
        adapter._account_id = "bot-acc"

        seen: list[MessageEvent] = []

        async def _capture(event: MessageEvent) -> None:
            seen.append(event)

        adapter.set_message_handler(_capture)
        adapter._maybe_fetch_typing_ticket = AsyncMock(return_value=None)

        await adapter._process_message(
            {
                "from_user_id": "peer-99",
                "message_id": "mid-1",
                "context_token": "ctx-token-xyz",
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": "冒烟消息"}}],
            }
        )

        assert len(seen) == 1
        ev = seen[0]
        assert ev.text == "冒烟消息"
        assert ev.message_type == MessageType.TEXT
        assert ev.source is not None
        assert ev.source.platform == "wechat"
        assert ev.source.chat_id
        assert adapter._token_store.get("bot-acc", "peer-99") == "ctx-token-xyz"

    @pytest.mark.asyncio
    async def test_process_message_photo_without_text(
        self, tmp_path, monkeypatch, tmp_butler_home
    ):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))

        def _fake_create_task(coro, *args, **kwargs):
            if asyncio.iscoroutine(coro):
                coro.close()
            return MagicMock()

        monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
        monkeypatch.setenv("BUTLER_GATEWAY_TYPING_ENABLED", "0")
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "0")

        adapter = WeChatAdapter(
            PlatformConfig(token="test-token", extra={"account_id": "bot-acc"}),
        )
        adapter._poll_session = MagicMock()
        adapter._account_id = "bot-acc"
        adapter._dm_policy = "open"
        adapter._maybe_fetch_typing_ticket = AsyncMock(return_value=None)

        async def _fake_download_image(item):
            del item
            return "/tmp/wechat-smoke.jpg"

        adapter._download_image = _fake_download_image

        seen: list[MessageEvent] = []

        async def _capture(event: MessageEvent) -> None:
            seen.append(event)

        adapter.set_message_handler(_capture)

        await adapter._process_message(
            {
                "from_user_id": "peer-img",
                "message_id": "mid-img",
                "context_token": "ctx-img",
                "item_list": [
                    {
                        "type": ITEM_IMAGE,
                        "image_item": {"encrypt_query_param": "fake"},
                    }
                ],
            }
        )

        assert len(seen) == 1
        ev = seen[0]
        assert ev.text == ""
        assert ev.message_type == MessageType.PHOTO
        assert ev.media_urls == ["/tmp/wechat-smoke.jpg"]
        assert ev.media_types == ["image/jpeg"]
        assert adapter._token_store.get("bot-acc", "peer-img") == "ctx-img"

    @pytest.mark.asyncio
    async def test_inbound_schedules_typing_fetch_with_context_token(
        self, monkeypatch, tmp_butler_home
    ):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
        fetch_calls: list[tuple[str, str | None]] = []
        pending: list = []

        async def _track_fetch(user_id: str, context_token=None):
            fetch_calls.append((user_id, context_token))

        def _fake_create_task(coro, *args, **kwargs):
            del args, kwargs
            pending.append(coro)
            return MagicMock()

        monkeypatch.setattr(asyncio, "create_task", _fake_create_task)
        monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "0")

        adapter = WeChatAdapter(
            PlatformConfig(token="test-token", extra={"account_id": "bot-acc"}),
        )
        adapter._poll_session = MagicMock()
        adapter._account_id = "bot-acc"
        adapter._dm_policy = "open"
        adapter._maybe_fetch_typing_ticket = _track_fetch
        adapter.set_message_handler(AsyncMock())

        await adapter._process_message(
            {
                "from_user_id": "peer-typ",
                "message_id": "mid-typ",
                "context_token": "ctx-typing",
                "item_list": [{"type": ITEM_TEXT, "text_item": {"text": "hi"}}],
            }
        )

        for coro in pending:
            await coro
        assert fetch_calls
        assert all(user == "peer-typ" and token == "ctx-typing" for user, token in fetch_calls)
