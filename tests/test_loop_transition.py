"""Loop transition_reason telemetry."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from butler.core.agent_loop import AgentLoop
from butler.core.loop_types import LoopConfig, LoopStatus, LoopTransitionReason


@pytest.mark.module_test
def test_turn_completed_sets_transition_reason(mock_llm_client, mock_llm_response):
    mock_llm_client.complete.return_value = mock_llm_response(content="done")
    loop = AgentLoop(mock_llm_client, config=LoopConfig(stream=False, max_iterations=5))
    result = loop.run("hello")
    assert result.status == LoopStatus.COMPLETED
    assert result.transition_reason == LoopTransitionReason.TURN_COMPLETED.value
    assert result.diagnostics.get("loop_transition_reason") == "turn_completed"


@pytest.mark.module_test
def test_tool_limit_sets_transition_reason(mock_llm_client):
    from butler.transport.types import NormalizedResponse

    mock_llm_client.complete.return_value = NormalizedResponse(
        content="",
        tool_calls=[
            __import__(
                "butler.transport.types", fromlist=["ToolCall"]
            ).ToolCall(id="t1", name="echo", arguments="{}"),
        ],
    )
    loop = AgentLoop(
        mock_llm_client,
        config=LoopConfig(stream=False, max_iterations=1),
        tool_dispatcher=lambda _n, _a: '{"ok": true}',
        tools=[{"type": "function", "function": {"name": "echo"}}],
    )
    with patch(
        "butler.core.tool_result_storage.maybe_spill_tool_result",
        side_effect=lambda r, **k: r,
    ):
        result = loop.run("run tool")
    assert result.status == LoopStatus.TOOL_LIMIT
    assert result.transition_reason == LoopTransitionReason.TOOL_LIMIT.value
