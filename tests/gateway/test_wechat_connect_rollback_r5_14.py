"""R5-14: WeChat connect rolls back partial setup on failure."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from butler.gateway.platforms.types import PlatformConfig
from butler.gateway.platforms.wechat_ilink import WeChatAdapter


@pytest.mark.asyncio
async def test_connect_disconnects_when_open_sessions_raises(monkeypatch):
    monkeypatch.setattr(
        "butler.gateway.platforms.wechat_ilink.check_wechat_requirements",
        lambda: True,
    )

    adapter = WeChatAdapter(
        PlatformConfig(token="test-token", extra={"account_id": "bot-acc"}),
    )

    poll_sess = MagicMock(spec=["closed", "close"])
    poll_sess.closed = False
    poll_sess.close = AsyncMock()
    send_sess = MagicMock(spec=["closed", "close"])
    send_sess.closed = False
    send_sess.close = AsyncMock()

    def _fake_open(ad: WeChatAdapter) -> None:
        ad._poll_session = poll_sess
        ad._send_session = send_sess

    monkeypatch.setattr(
        "butler.gateway.platforms.wechat_ilink.connect_phases._acquire_token_lock",
        lambda _ad: True,
    )
    monkeypatch.setattr(
        "butler.gateway.platforms.wechat_ilink.connect_phases._open_aiohttp_sessions",
        _fake_open,
    )

    def _boom(_ad: WeChatAdapter) -> None:
        raise RuntimeError("register failed")

    monkeypatch.setattr(
        "butler.gateway.platforms.wechat_ilink.connect_phases._start_poll_and_register",
        _boom,
    )

    ok = await adapter.connect()

    assert ok is False
    assert not adapter.is_connected
    poll_sess.close.assert_awaited_once()
    send_sess.close.assert_awaited_once()
