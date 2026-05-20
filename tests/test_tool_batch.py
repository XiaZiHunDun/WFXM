"""Unit tests for butler.core.tool_batch."""

from __future__ import annotations

import json

import pytest

from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.tool_batch import (
    dispatch_tool_with_envelope,
    finalize_fallback_tool_result,
    process_tool_calls,
)
from butler.transport.types import NormalizedResponse, Usage, build_tool_call


def _usage() -> Usage:
    return Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)


@pytest.mark.unit
def test_process_tool_calls_sequential_interrupt_fills_remaining_messages():
    from butler.tools.registry import reset_tool_audit_events

    reset_tool_audit_events()
    tc1 = build_tool_call("c1", "tool_a", {})
    tc2 = build_tool_call("c2", "tool_b", {})
    messages: list[dict] = []
    checks = {"count": 0}

    def interrupt_after_first() -> bool:
        checks["count"] += 1
        return checks["count"] > 1

    stats = process_tool_calls(
        response=NormalizedResponse(tool_calls=[tc1, tc2], usage=_usage()),
        messages=messages,
        config=LoopConfig(enable_parallel_tools=False),
        callbacks=LoopCallbacks(),
        guardrails=None,
        dispatch_tool=lambda _n, _a: json.dumps({"ok": True}),
        interrupt_check=interrupt_after_first,
    )

    assert stats.tools_started == 1
    tool_msgs = [msg for msg in messages if msg["role"] == "tool"]
    assert len(tool_msgs) == 2
    assert json.loads(tool_msgs[1]["content"])["code"] == "TOOL_INTERRUPTED"


@pytest.mark.unit
def test_dispatch_tool_with_envelope_wraps_failures():
    from butler.tools.registry import reset_tool_audit_events

    reset_tool_audit_events()

    result = dispatch_tool_with_envelope(
        lambda _n, _a: json.dumps({"error": "boom"}),
        "explode",
        {},
    )
    data = json.loads(result)
    assert data["ok"] is False
    assert data["code"] == "TOOL_ERROR"


@pytest.mark.unit
def test_finalize_fallback_tool_result_records_audit():
    from butler.execution_context import use_execution_context
    from butler.tools.registry import get_tool_audit_events, reset_tool_audit_events
    from types import SimpleNamespace

    reset_tool_audit_events()
    with use_execution_context(SimpleNamespace(), session_key="tool-batch"):
        finalize_fallback_tool_result(
            "missing",
            {},
            {"error": "x", "code": "TOOL_NOT_FOUND"},
        )
    events = get_tool_audit_events(session_key="tool-batch")
    assert len(events) == 1
    assert events[0]["code"] == "TOOL_NOT_FOUND"
