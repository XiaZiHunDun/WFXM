"""Gateway completion push policy and scheduling."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from butler.gateway.completion_notify import (
    build_turn_complete_text,
    should_push_delegate_completion,
    should_push_turn_completion,
    try_push_agent_report,
    try_push_turn_complete,
)
from butler.gateway.outbound_bridge import GatewayOutboundBridge
from butler.report import AgentReport


def _bridge(*, ack_sent: bool = False, elapsed: float = 120.0) -> GatewayOutboundBridge:
    loop = asyncio.new_event_loop()
    adapter = MagicMock()
    adapter.send = AsyncMock()
    br = GatewayOutboundBridge(adapter=adapter, chat_id="wx-user", loop=loop)
    br._started_at = __import__("time").monotonic() - elapsed
    br._ack_sent = ack_sent
    br._completion_push_sent = False
    return br


def test_should_push_delegate_when_ack_sent():
    br = _bridge(ack_sent=True, elapsed=10.0)
    assert should_push_delegate_completion(br, 10.0)


def test_should_not_push_turn_without_ack():
    br = _bridge(ack_sent=False, elapsed=200.0)
    assert not should_push_turn_completion(br, 200.0)


def test_should_push_turn_after_ack_and_min_elapsed(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS", "60")
    br = _bridge(ack_sent=True, elapsed=120.0)
    assert should_push_turn_completion(br, 120.0)


def test_try_push_agent_report_schedules_send(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE", "each")
    br = _bridge(ack_sent=True, elapsed=100.0)
    report = AgentReport(headline="开发代理已完成任务", summary="ok", success=True)

    def _run_coro(coro, loop):
        loop.run_until_complete(coro)
        return MagicMock()

    with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
        assert try_push_agent_report(
            report, kind="delegate", bridge=br, elapsed_turn_seconds=100.0
        )
    br.adapter.send.assert_called_once()
    text = br.adapter.send.call_args[0][1]
    assert "委派阶段完成" in text
    assert "已完成任务" in text
    br.loop.close()


def test_turn_complete_text():
    assert "90" in build_turn_complete_text(elapsed_seconds=95.0) or "分" in build_turn_complete_text(
        elapsed_seconds=95.0
    )


def test_try_push_turn_complete_respects_completion_sent_flag():
    br = _bridge(ack_sent=True, elapsed=120.0)
    br._completion_push_sent = True
    assert not try_push_turn_complete(br, elapsed_seconds=120.0)


def test_deliver_completion_push_enqueues_on_failure(tmp_path, monkeypatch):
    import asyncio

    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    adapter = MagicMock()
    adapter.send = AsyncMock(
        return_value=__import__(
            "butler.gateway.platforms.types", fromlist=["SendResult"]
        ).SendResult(success=False, error="rate limit exceeded")
    )
    ok = asyncio.run(
        __import__(
            "butler.gateway.completion_notify", fromlist=["deliver_completion_push"]
        ).deliver_completion_push(adapter, "wx-1", "body", kind="delegate")
    )
    assert ok is False
    queue = tmp_path / "runtime" / "push_queue.jsonl"
    assert queue.is_file()
    assert "完成提醒" in queue.read_text(encoding="utf-8")


def test_deliver_completion_push_waits_cooldown(monkeypatch):
    import asyncio

    calls: list[str] = []

    def _wait():
        calls.append("wait")
        return 0.0

    def _mark():
        calls.append("mark")

    monkeypatch.setattr("butler.runtime.notify.wait_wechat_push_cooldown", _wait)
    monkeypatch.setattr("butler.runtime.notify.mark_wechat_push_sent", _mark)
    adapter = MagicMock()
    adapter.send = AsyncMock(
        return_value=__import__(
            "butler.gateway.platforms.types", fromlist=["SendResult"]
        ).SendResult(success=True)
    )
    ok = asyncio.run(
        __import__(
            "butler.gateway.completion_notify", fromlist=["deliver_completion_push"]
        ).deliver_completion_push(adapter, "wx-1", "ok", kind="turn")
    )
    assert ok is True
    assert calls == ["wait", "mark"]


def test_workflow_failure_push(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    br = _bridge(ack_sent=True, elapsed=100.0)

    def _run_coro(coro, loop):
        loop.run_until_complete(coro)
        return MagicMock()

    with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
        from butler.gateway.completion_notify import try_push_workflow_failure

        assert try_push_workflow_failure(
            br,
            "daily_report",
            RuntimeError("step failed"),
            session_key="s1",
        )
    text = br.adapter.send.call_args[0][1]
    assert "工作流" in text
    assert "未完成" in text or "失败" in text
    br.loop.close()
