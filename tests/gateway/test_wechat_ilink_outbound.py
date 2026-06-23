"""WeChat iLink outbound: context_token echo, typing, session fallback (no live HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.gateway.platforms.types import PlatformConfig
from butler.gateway.platforms.wechat_ilink import (
    SESSION_EXPIRED_ERRCODE,
    TYPING_START,
    WeChatAdapter,
)


def _connected_adapter(monkeypatch, tmp_butler_home) -> WeChatAdapter:
    monkeypatch.setenv("BUTLER_HOME", str(tmp_butler_home))
    adapter = WeChatAdapter(
        PlatformConfig(token="api-token", extra={"account_id": "bot-acc"}),
    )
    adapter._account_id = "bot-acc"
    adapter._send_session = MagicMock()  # noqa: magicmock-no-spec
    adapter._token = "api-token"
    adapter._base_url = "https://ilink.test"
    adapter._send_chunk_retries = 2
    adapter._send_chunk_delay_seconds = 0
    adapter._send_chunk_retry_delay_seconds = 0
    adapter._split_multiline_messages = False
    return adapter


@pytest.mark.integration
class TestWechatIlinkOutboundSend:
    @pytest.mark.asyncio
    async def test_send_passes_stored_context_token(self, monkeypatch, tmp_butler_home):
        adapter = _connected_adapter(monkeypatch, tmp_butler_home)
        adapter._token_store.set("bot-acc", "peer-1", "ctx-outbound-99")
        captured: list[str | None] = []

        original = adapter._send_text_chunk

        async def _fake_chunk(*, chat_id, chunk, context_token, client_id):
            captured.append(context_token)

        adapter._send_text_chunk = _fake_chunk
        try:
            result = await adapter.send("peer-1", "你好 Butler")
        finally:
            adapter._send_text_chunk = original

        assert result.success is True
        assert captured == ["ctx-outbound-99"]

    @pytest.mark.asyncio
    async def test_send_text_chunk_retries_without_token_on_session_expired(
        self, monkeypatch, tmp_butler_home
    ):
        adapter = _connected_adapter(monkeypatch, tmp_butler_home)
        adapter._token_store.set("bot-acc", "peer-2", "stale-token")
        calls: list[str | None] = []

        async def _fake_attempt(adapter_self, *, chat_id, chunk, context_token, client_id):
            calls.append(context_token)
            if context_token:
                return {"ret": SESSION_EXPIRED_ERRCODE, "errcode": SESSION_EXPIRED_ERRCODE}
            return {"ret": 0}

        with patch(
            "butler.gateway.platforms.wechat_ilink_phases._phase_chunk_attempt",
            side_effect=_fake_attempt,
        ):
            await adapter._send_text_chunk(
                chat_id="peer-2",
                chunk="重试发送",
                context_token="stale-token",
                client_id="client-1",
            )

        assert calls == ["stale-token", None]
        assert adapter._token_store.get("bot-acc", "peer-2") is None


@pytest.mark.integration
class TestWechatIlinkOutboundTyping:
    @pytest.mark.asyncio
    async def test_send_typing_uses_cached_ticket(self, monkeypatch, tmp_butler_home):
        monkeypatch.setenv("BUTLER_GATEWAY_TYPING_ENABLED", "1")
        adapter = _connected_adapter(monkeypatch, tmp_butler_home)
        adapter._typing_cache.set("peer-3", "ticket-abc")

        with patch(
            "butler.gateway.platforms.wechat_ilink._send_typing",
            new_callable=AsyncMock,
        ) as mock_typing:
            await adapter.send_typing("peer-3")

        mock_typing.assert_awaited_once()
        kwargs = mock_typing.await_args.kwargs
        assert kwargs["typing_ticket"] == "ticket-abc"
        assert kwargs["status"] == TYPING_START

    @pytest.mark.asyncio
    async def test_get_config_passes_context_token_for_typing_fetch(
        self, monkeypatch, tmp_butler_home
    ):
        adapter = _connected_adapter(monkeypatch, tmp_butler_home)
        adapter._poll_session = MagicMock()  # noqa: magicmock-no-spec

        with patch(
            "butler.gateway.platforms.wechat_ilink._get_config",
            new_callable=AsyncMock,
            return_value={"typing_ticket": "ticket-xyz"},
        ) as mock_cfg:
            await adapter._maybe_fetch_typing_ticket("peer-4", "ctx-for-typing")

        mock_cfg.assert_awaited_once()
        assert mock_cfg.await_args.kwargs["context_token"] == "ctx-for-typing"
        assert adapter._typing_cache.get("peer-4") == "ticket-xyz"
