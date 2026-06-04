"""主线 M/N confirm: two-phase, risk ask, stuck, schema repair."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.core.confirm_flags import (
    permission_risk_heuristic_enabled,
    two_phase_confirm_enabled,
)
from butler.core.loop_stuck import guardrail_stuck_message
from butler.core.loop_types import LoopStatus
from butler.core.tool_batch import ToolBatchStats, process_tool_calls
from butler.core.two_phase_confirm import (
    clear_pending,
    is_high_risk_tool,
    load_pending,
    parse_confirm_command,
    save_pending,
    two_phase_block_message,
    try_execute_pending_confirm,
)
from butler.report import (
    AgentReport,
    enrich_output_schema,
    maybe_repair_structured_output,
    validate_structured_output,
)
from butler.report.format import wechat_response_text
from butler.tool_guardrails import GuardrailDecision, ToolCallGuardrailController
from butler.transport.types import NormalizedResponse, ToolCall
from butler.core.loop_types import LoopCallbacks, LoopConfig, LoopResult


def test_high_risk_tools():
    assert is_high_risk_tool("terminal", {"command": "ls"})
    assert is_high_risk_tool("delete_file", {"path": "x.txt"})


def test_two_phase_save_and_confirm(monkeypatch):
    monkeypatch.setenv("BUTLER_TWO_PHASE_CONFIRM", "1")
    assert two_phase_confirm_enabled()
    clear_pending("tp-sess")
    msg = two_phase_block_message(
        "delete_file",
        {"path": "secret.txt"},
        session_key="tp-sess",
        tool_call_id="c1",
    )
    assert msg is not None
    assert "确认工具" in msg
    assert load_pending("tp-sess") is not None
    assert parse_confirm_command("/确认工具")
    with patch("butler.tools.registry.dispatch_tool", return_value='{"ok":true}'):
        out = try_execute_pending_confirm("/确认工具", session_key="tp-sess")
    assert out is not None
    assert "已执行" in out
    assert load_pending("tp-sess") is None


def test_tool_batch_two_phase_waiting(monkeypatch):
    monkeypatch.setenv("BUTLER_TWO_PHASE_CONFIRM", "1")
    response = NormalizedResponse(
        tool_calls=[
            ToolCall(id="1", name="delete_file", arguments='{"path":"a.txt"}'),
        ],
    )
    messages: list[dict] = []

    def _dispatch(name: str, args: dict) -> str:
        block = two_phase_block_message(name, args, tool_call_id="1")
        if block:
            return json.dumps({"ok": False, "code": "TWO_PHASE_PENDING", "error": block})
        return '{"ok":true}'

    stats = process_tool_calls(
        response=response,
        messages=messages,
        config=LoopConfig(),
        callbacks=LoopCallbacks(),
        guardrails=None,
        dispatch_tool=_dispatch,
        interrupt_check=lambda: False,
    )
    assert stats.waiting_confirmation_message


def test_guardrail_stuck_message():
    g = ToolCallGuardrailController()
    g.set_halt_decision(
        GuardrailDecision(
            action="block",
            code="circuit",
            message="单轮工具调用已达上限",
            tool_name="read_file",
        )
    )
    assert guardrail_stuck_message(g) == "单轮工具调用已达上限"


def test_wechat_stuck_and_waiting():
    stuck = LoopResult(
        status=LoopStatus.STUCK,
        final_response="乒乓循环",
    )
    assert "卡住" in wechat_response_text(stuck)
    waiting = LoopResult(
        status=LoopStatus.WAITING_CONFIRMATION,
        final_response="请确认",
    )
    assert "确认" in wechat_response_text(waiting)


def test_validate_and_repair_schema(monkeypatch):
    monkeypatch.setenv("BUTLER_OUTPUT_SCHEMA_VALIDATE", "1")
    monkeypatch.setenv("BUTLER_OUTPUT_SCHEMA_REPAIR", "1")
    report = AgentReport()
    enrich_output_schema(
        report,
        '{"rating": "approve"}',
        {
            "fields": [
                {"name": "rating", "type": "string", "required": True},
                {"name": "score", "type": "integer", "required": True},
            ],
        },
    )
    assert any("schema:" in i for i in report.issues)
    mock_client = MagicMock()  # noqa: magicmock-no-spec — external agent confirm facade (mock client / orch)
    mock_client.complete.return_value = NormalizedResponse(
        content='{"rating": "approve", "score": 8}',
    )
    orch = MagicMock()  # noqa: magicmock-no-spec — external agent confirm facade (mock client / orch)
    orch.create_llm_client.return_value = mock_client
    repaired = maybe_repair_structured_output(
        report,
        '{"rating": "approve"}',
        {
            "fields": [
                {"name": "rating", "type": "string"},
                {"name": "score", "type": "integer", "required": True},
            ],
        },
        orchestrator=orch,
    )
    ok, errs = validate_structured_output(repaired.structured_output, {
        "fields": [{"name": "score", "type": "integer", "required": True}],
    })
    assert repaired.structured_output.get("score") == 8


def test_permission_risk_heuristic_flag(monkeypatch):
    monkeypatch.setenv("BUTLER_PERMISSION_RISK_HEURISTIC", "1")
    assert permission_risk_heuristic_enabled()
