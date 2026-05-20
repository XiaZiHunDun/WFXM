"""P3: WeChat iLink media download helpers (mocked HTTP, no live CDN)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.gateway.platforms.types import MessageEvent, MessageType, PlatformConfig
from butler.gateway.platforms.wechat_ilink import (
    ITEM_IMAGE,
    WeChatAdapter,
    _assert_wechat_cdn_url,
    _download_and_decrypt_media,
)


@pytest.mark.unit
class TestWechatCdnUrlGuard:
    def test_rejects_non_allowlisted_host(self):
        with pytest.raises(ValueError, match="allowlist"):
            _assert_wechat_cdn_url("https://evil.example.com/secret.jpg")

    def test_accepts_wechat_cdn_host(self):
        _assert_wechat_cdn_url("https://novac2c.cdn.wechat.qq.com/c2c/blob")


@pytest.mark.integration
class TestDownloadAndDecryptMedia:
    @pytest.mark.asyncio
    async def test_download_via_encrypted_query_param(self):
        session = MagicMock()
        payload = b"encrypted-payload"

        with patch(
            "butler.gateway.platforms.wechat_ilink._download_bytes",
            new_callable=AsyncMock,
            return_value=payload,
        ) as mock_dl:
            out = await _download_and_decrypt_media(
                session,
                cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
                encrypted_query_param="enc-query-1",
                aes_key_b64=None,
                full_url=None,
                timeout_seconds=5.0,
            )

        assert out == payload
        mock_dl.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_download_via_allowlisted_full_url(self):
        session = MagicMock()
        payload = b"raw-image"

        with patch(
            "butler.gateway.platforms.wechat_ilink._download_bytes",
            new_callable=AsyncMock,
            return_value=payload,
        ):
            out = await _download_and_decrypt_media(
                session,
                cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
                encrypted_query_param=None,
                aes_key_b64=None,
                full_url="https://mmbiz.qpic.cn/mmbiz/test.jpg",
                timeout_seconds=5.0,
            )

        assert out == payload

    @pytest.mark.asyncio
    async def test_raises_when_no_media_reference(self):
        session = MagicMock()
        with pytest.raises(RuntimeError, match="neither"):
            await _download_and_decrypt_media(
                session,
                cdn_base_url="https://novac2c.cdn.weixin.qq.com/c2c",
                encrypted_query_param=None,
                aes_key_b64=None,
                full_url=None,
                timeout_seconds=5.0,
            )


@pytest.mark.integration
class TestInboundMediaFailure:
    @pytest.mark.asyncio
    async def test_image_download_failure_does_not_emit_event(
        self, monkeypatch, tmp_butler_home
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

        async def _fail_image(item):
            del item
            return None

        adapter._download_image = _fail_image

        seen: list[MessageEvent] = []

        async def _capture(ev: MessageEvent) -> None:
            seen.append(ev)

        adapter.set_message_handler(_capture)

        await adapter._process_message(
            {
                "from_user_id": "peer-fail",
                "message_id": "mid-fail",
                "item_list": [
                    {
                        "type": ITEM_IMAGE,
                        "image_item": {"encrypt_query_param": "bad"},
                    }
                ],
            }
        )

        assert seen == []
