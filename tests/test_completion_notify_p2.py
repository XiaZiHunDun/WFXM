"""P2: delegate last mode, timeout push, SubagentStop hooks."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from butler.gateway.completion_notify import (
    delegate_completion_mode,
    flush_pending_delegate_completion,
    try_push_agent_report,
    try_push_turn_timeout,
)
from butler.gateway.outbound_bridge import GatewayOutboundBridge
from butler.report import AgentReport


def _bridge(*, ack_sent: bool = True, elapsed: float = 120.0) -> GatewayOutboundBridge:
    loop = asyncio.new_event_loop()
    adapter = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    adapter.send = AsyncMock(  # noqa: magicmock-no-spec — complex facade, spec= 收益低
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
    return MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低


def test_delegate_last_mode_only_pushes_on_flush(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE", "last")
    assert delegate_completion_mode() == "last"
    br = _bridge(ack_sent=True)
    r1 = AgentReport(headline="第一次", summary="a", success=True)
    r2 = AgentReport(headline="第二次", summary="b", success=True)

    with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
        assert try_push_agent_report(r1, kind="delegate", bridge=br) is True
        assert br.adapter.send.call_count == 0
        assert try_push_agent_report(r2, kind="delegate", bridge=br) is True
        assert br.adapter.send.call_count == 0
        flush_pending_delegate_completion(br)
        assert br.adapter.send.call_count == 1
        text = br.adapter.send.call_args[0][1]
        assert "第二次" in text
    br.loop.close()


def test_timeout_push_when_ack_sent(monkeypatch):
    monkeypatch.setenv("BUTLER_GATEWAY_TIMEOUT_COMPLETION_NOTIFY", "1")
    br = _bridge(ack_sent=True, elapsed=200.0)
    with patch("asyncio.run_coroutine_threadsafe", side_effect=_run_coro):
        assert try_push_turn_timeout(br, timeout_seconds=600, elapsed_seconds=200.0)
        assert br.adapter.send.call_count == 1
        assert "超时" in br.adapter.send.call_args[0][1]
    br.loop.close()


def test_subagent_stop_hook_runs(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
    from butler.config import reload_butler_settings

    reload_butler_settings()
    marker = tmp_path / "subagent_stop.marker"
    hook = tmp_path / "stop.sh"
    hook.write_text(f"#!/bin/sh\ntouch {marker}\n", encoding="utf-8")
    hooks_dir = tmp_path / ".butler"
    hooks_dir.mkdir(exist_ok=True)
    (hooks_dir / "hooks.yaml").write_text(
        f"""hooks:
  SubagentStop:
    - matcher: dev
      command: sh {hook}
""",
        encoding="utf-8",
    )
    from butler.hooks.runner import run_subagent_stop_hooks

    run_subagent_stop_hooks(
        agent_type="dev",
        agent_id="t1",
        success=True,
        session_key="s1",
        summary_preview="done",
    )
    assert marker.is_file()
