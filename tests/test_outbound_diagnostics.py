"""Outbound completion diagnostics and push queue helpers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from butler.gateway import completion_notify
from butler.gateway.completion_telemetry import (
    completion_push_stats,
    record_completion_push_sent,
    reset_completion_telemetry,
)
from butler.runtime import push_queue


def test_format_outbound_diagnostic_lines_includes_policy(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_COMPLETION_NOTIFY", "1")
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE", "last")
    reset_completion_telemetry()
    lines = completion_notify.format_outbound_diagnostic_lines("sess-1")
    assert any("出站策略" in ln for ln in lines)
    assert any("委派=last" in ln for ln in lines)
    assert any("出站推送本轮" in ln for ln in lines)


def test_completion_push_stats_after_record():
    reset_completion_telemetry("sk")
    record_completion_push_sent(session_key="sk")
    stats = completion_push_stats("sk")
    assert stats["sent"] == 1
    reset_completion_telemetry("sk")
    assert completion_push_stats("sk")["sent"] == 0


def test_count_pending_pushes_filters_chat_id(tmp_path, monkeypatch):
    q = tmp_path / "push_queue.jsonl"
    rows = [
        {"chat_id": "a", "title": "t", "body": "b"},
        {"chat_id": "b", "title": "t", "body": "b"},
    ]
    q.write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    monkeypatch.setattr(push_queue, "_queue_path", lambda: q)
    assert push_queue.count_pending_pushes() == 2
    assert push_queue.count_pending_pushes(chat_id="a") == 1


@pytest.mark.asyncio
async def test_deliver_completion_push_records_sent(monkeypatch):
    reset_completion_telemetry()
    monkeypatch.setattr(
        completion_notify,
        "wait_wechat_push_cooldown",
        lambda: None,
        raising=False,
    )
    import butler.runtime.notify as notify

    monkeypatch.setattr(notify, "wait_wechat_push_cooldown", lambda: None)
    monkeypatch.setattr(notify, "mark_wechat_push_sent", lambda: None)

    adapter = MagicMock()
    adapter.send = AsyncMock(return_value=MagicMock(success=True, error=None))

    ok = await completion_notify.deliver_completion_push(
        adapter,
        "chat-99",
        "body",
        kind="turn",
    )
    assert ok is True
    stats = completion_push_stats("chat-99")
    assert stats["sent"] == 1
    reset_completion_telemetry()
