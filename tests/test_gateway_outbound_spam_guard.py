"""Guard against redundant WeChat outbound spam per inbound turn."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from butler.gateway.completion_notify import (
    flush_pending_delegate_completion,
    try_push_turn_complete,
)
from butler.gateway.outbound_bridge import GatewayOutboundBridge
from butler.report import AgentReport


def _bridge(*, ack_sent: bool = True, elapsed: float = 120.0) -> GatewayOutboundBridge:
    loop = asyncio.new_event_loop()
    adapter = MagicMock()  # noqa: magicmock-no-spec
    adapter.send = AsyncMock(
        return_value=__import__(
            "butler.gateway.platforms.types", fromlist=["SendResult"]
        ).SendResult(success=True)
    )
    br = GatewayOutboundBridge(adapter=adapter, chat_id="wx-user", loop=loop)
    br._started_at = __import__("time").monotonic() - elapsed
    br._ack_sent = ack_sent
    return br


def _run_coro(coro, loop):
    loop.run_until_complete(coro)
    return MagicMock()  # noqa: magicmock-no-spec


def test_flush_delegate_skipped_after_main_reply(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE", "last")
    monkeypatch.setenv("BUTLER_GATEWAY_SUPPRESS_COMPLETION_AFTER_MAIN", "1")
    br = _bridge(ack_sent=True)
    report = AgentReport(headline="委派完成", summary="ok", success=True)
    br.set_pending_delegate_report(report)
    br.mark_final_sent(main_reply_chars=120)

    with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
        assert flush_pending_delegate_completion(br) is False
        assert br.adapter.send.call_count == 0
    br.loop.close()


def test_turn_complete_suppressed_after_main_reply(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_SUPPRESS_COMPLETION_AFTER_MAIN", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS", "60")
    br = _bridge(ack_sent=True, elapsed=120.0)
    br.mark_final_sent(main_reply_chars=80)

    with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
        assert not try_push_turn_complete(br, elapsed_seconds=120.0)
        assert br.adapter.send.call_count == 0
    br.loop.close()


def test_supplementary_cap_per_turn(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_MAX_SUPPLEMENTARY_PER_TURN", "1")
    br = _bridge()
    assert br.schedule_supplementary_reply("first", kind="queued")
    assert not br.schedule_supplementary_reply("second", kind="queued")
    br.loop.close()


def test_queued_supplementary_blocked_after_final(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_MAX_SUPPLEMENTARY_PER_TURN", "3")
    br = _bridge()
    br.mark_final_sent(main_reply_chars=50)
    assert not br.schedule_supplementary_reply("queued follow-up", kind="queued")
    br.loop.close()
