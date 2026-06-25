"""Tests for recorded LLM response fixtures (orchestration replay, no live API)."""

from __future__ import annotations

import json

import pytest

from butler.core.agent_loop import AgentLoop, LoopConfig, LoopStatus
from butler.tools.registry import dispatch_tool, get_tool_definitions
from tests.fixtures.llm_responses import (
    load_llm_script,
    mock_client_from_script,
    responses_from_script,
)


@pytest.mark.module_test
def test_load_llm_script_text_only():
    script = load_llm_script("text_only.json")
    responses = responses_from_script(script)
    assert len(responses) == 1
    assert responses[0].content == "你好，我是 Butler 测试夹具。"


@pytest.mark.module_test
def test_mock_client_plays_script_in_order():
    client = mock_client_from_script(load_llm_script("delegate_tool_then_done.json"))
    first = client.complete(messages=[])
    second = client.complete(messages=[])
    assert first.tool_calls
    assert first.tool_calls[0].name == "delegate_task"
    assert second.content == "已委派开发代理，完成后会通知你。"


@pytest.mark.module_test
def test_scripted_text_only_loop():
    client = mock_client_from_script(load_llm_script("text_only.json"))
    loop = AgentLoop(client, config=LoopConfig(stream=False))
    result = loop.run("ping")
    assert result.status == LoopStatus.COMPLETED
    assert "Butler 测试夹具" in (result.final_response or "")
    assert result.iterations == 1
    assert result.tool_calls_made == 0


@pytest.mark.module_test
def test_scripted_read_file_loop(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "README.md").write_text("# DemoPilot\n", encoding="utf-8")
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))

    client = mock_client_from_script(load_llm_script("read_file_then_answer.json"))
    tools = [t for t in get_tool_definitions() if t["function"]["name"] == "read_file"]
    loop = AgentLoop(
        client,
        tools=tools,
        tool_dispatcher=dispatch_tool,
        config=LoopConfig(stream=False),
    )
    result = loop.run("读 README")
    assert result.status == LoopStatus.COMPLETED
    assert "DemoPilot" in (result.final_response or "")
    assert result.tool_calls_made == 1
    assert client.complete.call_count == 2


@pytest.mark.module_test
def test_scripted_delegate_tool_then_summary():
    client = mock_client_from_script(load_llm_script("delegate_tool_then_done.json"))
    tools = [t for t in get_tool_definitions() if t["function"]["name"] == "delegate_task"]

    def _dispatch(name: str, args: dict, **_kw):
        if name == "delegate_task":
            return json.dumps(
                {
                    "success": True,
                    "summary": "dev done",
                    "task_id": "task_fixture01",
                    "role": args.get("role"),
                },
                ensure_ascii=False,
            )
        raise AssertionError(f"unexpected tool: {name}")

    loop = AgentLoop(
        client,
        tools=tools,
        tool_dispatcher=_dispatch,
        config=LoopConfig(stream=False),
    )
    result = loop.run("请委派开发写 docs")

    assert result.status == LoopStatus.COMPLETED
    assert result.tool_calls_made == 1
    assert "委派" in (result.final_response or "")
