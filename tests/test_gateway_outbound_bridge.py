"""Tests for gateway outbound UX bridge (typing, ack, milestones)."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from butler.gateway.outbound_bridge import (
    GatewayOutboundBridge,
    get_current_bridge,
    merge_loop_callbacks,
    set_current_bridge,
)
from butler.core.loop_types import LoopCallbacks


class _MockAdapter:
    def __init__(self) -> None:
        self.typing_calls = 0
        self.stop_calls = 0
        self.sent: list[str] = []

    async def send_typing(self, chat_id: str, metadata=None) -> None:
        del chat_id, metadata
        self.typing_calls += 1

    async def stop_typing(self, chat_id: str) -> None:
        del chat_id
        self.stop_calls += 1

    async def send(self, chat_id: str, content: str, reply_to=None, metadata=None):
        del chat_id, reply_to, metadata
        self.sent.append(content)
        return MagicMock(success=True)


@pytest.mark.asyncio
async def test_start_end_turn_typing_lifecycle(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "0")
    adapter = _MockAdapter()
    loop = asyncio.get_running_loop()
    bridge = GatewayOutboundBridge(adapter=adapter, chat_id="u1", loop=loop)

    await bridge.start_turn()
    assert adapter.typing_calls >= 1
    bridge.mark_final_sent()
    await bridge.end_turn()
    assert adapter.stop_calls == 1


@pytest.mark.asyncio
async def test_ack_sent_once_after_delay(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_SECONDS", "0.05")
    monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_TYPING_ENABLED", "0")
    adapter = _MockAdapter()
    loop = asyncio.get_running_loop()
    bridge = GatewayOutboundBridge(adapter=adapter, chat_id="u1", loop=loop)
    await bridge.start_turn()
    bridge.delegate_role = "content_agent"
    await asyncio.sleep(0.12)
    assert len(adapter.sent) == 1
    assert "content_agent" in adapter.sent[0]
    await bridge.end_turn()
    await asyncio.sleep(0.05)
    assert len(adapter.sent) == 1


@pytest.mark.asyncio
async def test_ack_skipped_when_final_sent_early(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_SECONDS", "0.2")
    monkeypatch.setenv("BUTLER_GATEWAY_TYPING_ENABLED", "0")
    adapter = _MockAdapter()
    loop = asyncio.get_running_loop()
    bridge = GatewayOutboundBridge(adapter=adapter, chat_id="u1", loop=loop)

    await bridge.start_turn()
    bridge.mark_final_sent()
    await asyncio.sleep(0.25)
    assert adapter.sent == []
    await bridge.end_turn()


def test_thread_local_bridge_roundtrip():
    adapter = _MockAdapter()
    loop = asyncio.new_event_loop()
    bridge = GatewayOutboundBridge(adapter=adapter, chat_id="c1", loop=loop)
    set_current_bridge(bridge)
    assert get_current_bridge() is bridge
    set_current_bridge(None)
    assert get_current_bridge() is None
    loop.close()


def test_merge_loop_callbacks_prefers_extra():
    base = LoopCallbacks(on_tool_start=lambda n, a: None)
    extra = LoopCallbacks(on_tool_complete=lambda n, r: None)
    merged = merge_loop_callbacks(base, extra)
    assert merged.on_tool_start is not None
    assert merged.on_tool_complete is not None


@pytest.mark.asyncio
async def test_delegate_milestone_threadsafe(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_TYPING_ENABLED", "0")
    monkeypatch.setenv("BUTLER_GATEWAY_PROGRESS_ACK_ENABLED", "0")
    adapter = _MockAdapter()
    loop = asyncio.get_running_loop()
    bridge = GatewayOutboundBridge(adapter=adapter, chat_id="u1", loop=loop)
    await bridge.start_turn()

    def _notify():
        bridge.notify_delegate_start("dev_agent")

    await asyncio.to_thread(_notify)
    await asyncio.sleep(0.02)
    assert bridge.delegate_role == "dev_agent"
    await bridge.end_turn()
