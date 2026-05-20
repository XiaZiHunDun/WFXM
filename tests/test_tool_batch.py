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
def test_parallel_batch_skips_dispatch_after_guardrail_halt():
    from butler.core.parallel_tools import execute_tools_parallel
    from butler.tool_guardrails import GuardrailConfig, GuardrailDecision, ToolCallGuardrailController
    from butler.transport.types import build_tool_call

    guardrails = ToolCallGuardrailController(
        GuardrailConfig(
            same_tool_failure_halt_after=99,
            same_tool_failure_warn_after=99,
            exact_failure_warn_after=99,
            exact_failure_block_after=99,
        )
    )
    halt = GuardrailDecision(
        action="halt",
        code="same_tool_failure_halt",
        message="Stopped search_files: failed 1 times this turn.",
        tool_name="search_files",
        count=1,
    )
    dispatched: list[str] = []

    def dispatch(name: str, _args: dict) -> str:
        dispatched.append(name)
        guardrails.set_halt_decision(halt)
        return json.dumps({"error": "fail"})

    def precheck(name: str, args: dict) -> str | None:
        if guardrails.halt_decision:
            return finalize_fallback_tool_result(
                name,
                args,
                {
                    "error": guardrails.halt_decision.message,
                    "guardrail": {
                        "action": guardrails.halt_decision.action,
                        "code": guardrails.halt_decision.code,
                        "count": guardrails.halt_decision.count,
                    },
                },
            )
        return None

    tool_calls = [
        build_tool_call(f"c{i}", "search_files", {"query": f"q{i}"})
        for i in range(4)
    ]
    pairs = execute_tools_parallel(
        tool_calls,
        dispatch,
        precheck_tool=precheck,
    )

    assert len(dispatched) == 1
    assert len(pairs) == 4
    skipped_payloads = [
        json.loads(result)
        for _tc, result in pairs
        if json.loads(result).get("guardrail", {}).get("action") == "halt"
    ]
    assert len(skipped_payloads) == 3


@pytest.mark.unit
def test_sequential_batch_skips_remaining_after_guardrail_halt():
    from butler.tool_guardrails import GuardrailConfig, GuardrailDecision, ToolCallGuardrailController
    from butler.transport.types import NormalizedResponse, Usage, build_tool_call

    guardrails = ToolCallGuardrailController(
        GuardrailConfig(
            same_tool_failure_halt_after=99,
            same_tool_failure_warn_after=99,
            exact_failure_warn_after=99,
            exact_failure_block_after=99,
        )
    )
    halt = GuardrailDecision(
        action="halt",
        code="same_tool_failure_halt",
        message="halt",
        tool_name="search_files",
        count=1,
    )
    dispatched: list[str] = []

    def dispatch(name: str, _args: dict) -> str:
        dispatched.append(name)
        if len(dispatched) == 1:
            guardrails.set_halt_decision(halt)
        return json.dumps({"error": "fail"})

    tool_calls = [
        build_tool_call(f"c{i}", "search_files", {"query": f"q{i}"})
        for i in range(3)
    ]
    messages: list[dict] = []
    stats = process_tool_calls(
        response=NormalizedResponse(tool_calls=tool_calls, usage=Usage(1, 1, 2)),
        messages=messages,
        config=LoopConfig(enable_parallel_tools=False),
        callbacks=LoopCallbacks(),
        guardrails=guardrails,
        dispatch_tool=dispatch,
        interrupt_check=lambda: False,
    )

    assert len(dispatched) == 1
    assert stats.tools_started == 1
    tool_msgs = [json.loads(msg["content"]) for msg in messages if msg["role"] == "tool"]
    assert len(tool_msgs) == 3
    assert sum(1 for payload in tool_msgs if payload.get("guardrail", {}).get("action") == "halt") == 2


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
