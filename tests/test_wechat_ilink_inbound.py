"""WeChat iLink inbound parsing (maps to transport layer smoke, no live HTTP)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from butler.gateway.platforms.types import MessageEvent, MessageType, PlatformConfig
from butler.gateway.platforms.wechat_ilink import (
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
