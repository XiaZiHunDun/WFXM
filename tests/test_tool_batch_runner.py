"""Unit tests for tool_batch_runner (P1-C)."""

from __future__ import annotations

import json

import pytest

from butler.core.loop_types import LoopCallbacks, LoopConfig
from butler.core.tool_batch import process_tool_calls
from butler.core.tool_batch_runner import extract_batch_followups
from butler.transport.types import NormalizedResponse, Usage, build_tool_call


def _usage() -> Usage:
    return Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2)


@pytest.mark.unit
def test_extract_batch_followups_clarification():
    tc = build_tool_call("c1", "ask_clarification", {})
    payload = json.dumps({"code": "CLARIFICATION", "question": "Which file?"})
    clar, waiting = extract_batch_followups([(tc, payload)])
    assert clar == "Which file?"
    assert waiting is None


@pytest.mark.unit
def test_extract_batch_followups_two_phase_pending():
    tc = build_tool_call("c1", "write_file", {"path": "/tmp/x"})
    payload = json.dumps({"code": "TWO_PHASE_PENDING", "error": "confirm?"})
    clar, waiting = extract_batch_followups([(tc, payload)])
    assert waiting == "confirm?"
    assert clar is None


@pytest.mark.unit
def test_runner_sequential_path_via_process_tool_calls():
    tc = build_tool_call("c1", "echo", {"x": 1})
    messages: list[dict] = []
    stats = process_tool_calls(
        response=NormalizedResponse(tool_calls=[tc], usage=_usage()),
        messages=messages,
        config=LoopConfig(enable_parallel_tools=False),
        callbacks=LoopCallbacks(),
        guardrails=None,
        dispatch_tool=lambda _n, _a: json.dumps({"ok": True}),
        interrupt_check=lambda: False,
    )
    assert stats.tools_started == 1
    assert any(m.get("role") == "tool" for m in messages)
