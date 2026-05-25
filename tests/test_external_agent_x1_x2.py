"""PR-X1/X2: external-agent-reports workflow + loop safety subsets."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.core.finish_tool_truncate import truncate_tool_calls_at_finish
from butler.core.safety_finish import safety_finish_user_message
from butler.core.skill_compact_rescue import extract_skill_rescue_messages
from butler.core.workflow_flags import workflow_optional_enabled, workflow_rescue_enabled
from butler.task_orchestrator import (
    AgentResult,
    AgentSpawnConfig,
    TaskNode,
    _first_failed_dependency,
    _graph_all_required_ok,
)
from butler.transport.types import NormalizedResponse, ToolCall
from butler.workflows.schema import parse_step
from butler.workflows.workflow_run_snapshot import build_run_snapshot, write_workflow_run_snapshot


def test_parse_step_optional_and_rescue():
    step = parse_step(
        {
            "id": "impl",
            "role": "dev",
            "task": "do work",
            "optional": True,
            "rescue_steps": [
                {"id": "diag", "role": "dev", "task": "summarize failure"},
            ],
        }
    )
    assert step is not None
    assert step.optional is True
    assert len(step.rescue_steps) == 1
    assert step.rescue_steps[0].id == "diag"


def test_optional_dependency_does_not_block():
    node_map = {
        "a": TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="t"), optional=True),
        "b": TaskNode(
            id="b",
            config=AgentSpawnConfig(role="dev", task="t2"),
            depends_on=["a"],
        ),
    }
    completed = {"a": AgentResult(success=False, error="fail")}
    assert workflow_optional_enabled()
    assert _first_failed_dependency(node_map["b"], completed, node_map) == ""
    assert _graph_all_required_ok(completed, node_map) is True


def test_graph_fails_when_required_step_fails():
    node_map = {
        "a": TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="t"), optional=False),
    }
    completed = {"a": AgentResult(success=False)}
    assert _graph_all_required_ok(completed, node_map) is False


def test_safety_finish_blocks_tool_calls():
    resp = NormalizedResponse(
        content="",
        tool_calls=[ToolCall(id="1", name="read_file", arguments="{}")],
        finish_reason="content_filter",
    )
    msg = safety_finish_user_message(resp)
    assert msg is not None
    assert "安全" in msg or "content_filter" in msg


def test_finish_tool_truncate():
    calls = [
        ToolCall(id="1", name="read_file", arguments="{}"),
        ToolCall(id="2", name="finish", arguments="{}"),
        ToolCall(id="3", name="read_file", arguments="{}"),
    ]
    out = truncate_tool_calls_at_finish(calls)
    assert len(out) == 2
    assert out[-1].name == "finish"


def test_skill_rescue_extract():
    messages = [
        {"role": "user", "content": "hi"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "id": "c1",
                    "type": "function",
                    "function": {
                        "name": "read_file",
                        "arguments": '{"path": ".butler/skills/foo.md"}',
                    },
                }
            ],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "skill body"},
    ]
    body, rescued = extract_skill_rescue_messages(messages, max_pairs=2)
    assert len(rescued) >= 2
    assert len(body) < len(messages)


def test_workflow_run_snapshot_write():
    with tempfile.TemporaryDirectory() as tmp:
        ws = Path(tmp)
        from butler.task_orchestrator import TaskGraphResult

        graph = TaskGraphResult(
            nodes={"x": AgentResult(success=False, error="boom")},
            execution_order=["x"],
            success=False,
        )
        path = write_workflow_run_snapshot(ws, "dev-qa-loop", graph, session_key="sk1")
        assert path is not None
        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["failed_steps"] == ["x"]


@pytest.mark.asyncio
async def test_rescue_steps_run_after_failure():
    from butler.task_orchestrator import TaskOrchestrator

    assert workflow_rescue_enabled()
    orch = TaskOrchestrator()
    node = TaskNode(
        id="main",
        config=AgentSpawnConfig(role="dev", task="fail task"),
        max_retries=1,
        rescue_configs=[
            AgentSpawnConfig(role="dev", task="rescue summarize"),
        ],
    )
    fail = AgentResult(success=False, error="primary failed", response="partial")
    ok_rescue = AgentResult(success=True, response="rescue output")

    with patch.object(orch, "spawn_agent", new_callable=AsyncMock) as mock_spawn:
        mock_spawn.return_value = ok_rescue
        out = await orch._run_rescue_steps(node, fail)
    assert "rescue output" in (out.response or "")
    assert out.success is False
    mock_spawn.assert_called_once()
