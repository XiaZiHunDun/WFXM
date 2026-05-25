"""Sprint Codex-C1: steer bridge, MCP approval, goal budget, orchestrator."""

from __future__ import annotations

import json
import os
from unittest.mock import patch

from butler.core.compaction_steer_bridge import apply_compaction_turn_followup
from butler.core.goal_loop import (
    goal_token_budget_default,
    record_goal_tokens,
    start_goal_loop,
)
from butler.gateway.message_queue import enqueue_inbound, pop_urgent_inbound
from butler.mcp.approval import format_mcp_approval_message, mcp_tool_fingerprint


def test_apply_compaction_steer_followup():
    messages = [{"role": "user", "content": "task"}]
    with patch.dict(os.environ, {"BUTLER_COMPACTION_INBOUND_BRIDGE": "1"}, clear=False):
        from butler.core.steer import steer

        steer("改成方案 B", session_key="sk1")
        out = apply_compaction_turn_followup(messages, "sk1", {})
    assert len(out) > len(messages)
    assert any("指引" in str(m.get("content") or "") for m in out)


def test_pop_urgent_inbound():
    with patch.dict(os.environ, {"BUTLER_GATEWAY_MESSAGE_QUEUE": "1"}, clear=False):
        enqueue_inbound("sk2", "/urgent 停", priority="now")
        item = pop_urgent_inbound("sk2")
    assert item is not None
    assert "停" in item.text


def test_mcp_approval_fingerprint_stable():
    a = mcp_tool_fingerprint("srv", "tool_x", {"q": 1})
    b = mcp_tool_fingerprint("srv", "tool_x", {"q": 1})
    assert a == b


def test_mcp_approval_message_format():
    msg = format_mcp_approval_message(
        server_id="fetch",
        tool_name="mcp_fetch_tool",
        args={"url": "https://example.com"},
        classification="network",
    )
    assert "MCP" in msg
    assert "fetch" in msg


def test_goal_token_budget_exhaust():
    with patch.dict(os.environ, {"BUTLER_GOAL_TOKEN_BUDGET": "1000"}, clear=False):
        start_goal_loop("sk3", "test goal", max_iterations=5)
        assert goal_token_budget_default() == 1000
        assert record_goal_tokens("sk3", 1200) is True
        from butler.core.goal_loop import goal_budget_exhausted_message

        msg = goal_budget_exhausted_message("sk3")
    assert msg is not None
    assert "预算" in msg


def test_tool_orchestrator_deny():
    from butler.core.tool_orchestrator import run_with_approval_gate

    out = run_with_approval_gate(
        tool_name="x",
        run_fn=lambda: json.dumps({"ok": True}),
        approval_fn=lambda: "blocked",
    )
    data = json.loads(out)
    assert data.get("ok") is False
