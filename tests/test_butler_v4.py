"""Butler v4 Test Suite — Self-contained Agent Loop Architecture.

Tests the new architecture where Butler controls its own Agent Loop
and uses Hermes only as a module source for transport/gateway.
"""

import json
import asyncio
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path


# ── Transport Layer ──────────────────────────────────────────

class TestTransportTypes:
    def test_tool_call_creation(self):
        from butler.transport.types import ToolCall, build_tool_call
        tc = build_tool_call("id1", "test_tool", {"key": "value"})
        assert tc.name == "test_tool"
        assert tc.id == "id1"
        assert json.loads(tc.arguments) == {"key": "value"}
        assert tc.type == "function"

    def test_normalized_response(self):
        from butler.transport.types import NormalizedResponse, Usage
        resp = NormalizedResponse(
            content="hello",
            finish_reason="stop",
            usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
        )
        assert resp.content == "hello"
        assert resp.usage.total_tokens == 15

    def test_tool_call_args_dict(self):
        from butler.transport.types import ToolCall
        tc = ToolCall(id="1", name="test", arguments='{"a": 1}')
        assert tc.args_dict() == {"a": 1}

    def test_map_finish_reason(self):
        from butler.transport.types import map_finish_reason
        assert map_finish_reason(None) == "stop"
        assert map_finish_reason("tool_calls") == "tool_calls"
        assert map_finish_reason("x", {"x": "y"}) == "y"


class TestTransportRegistry:
    def test_list_transports(self):
        from butler.transport import list_transports
        modes = list_transports()
        assert "chat_completions" in modes
        assert "anthropic_messages" in modes

    def test_get_transport(self):
        from butler.transport import get_transport
        cc = get_transport("chat_completions")
        assert cc is not None
        assert cc.api_mode == "chat_completions"

    def test_unknown_transport(self):
        from butler.transport import get_transport
        assert get_transport("nonexistent_mode") is None


class TestChatCompletionsTransport:
    def test_build_kwargs(self):
        from butler.transport.chat_completions import ChatCompletionsTransport
        t = ChatCompletionsTransport()
        kw = t.build_kwargs(
            model="gpt-4",
            messages=[{"role": "user", "content": "hi"}],
            temperature=0.7,
            max_tokens=100,
        )
        assert kw["model"] == "gpt-4"
        assert kw["temperature"] == 0.7
        assert kw["max_tokens"] == 100

    def test_normalize_dict_response(self):
        from butler.transport.chat_completions import ChatCompletionsTransport
        t = ChatCompletionsTransport()
        raw = {
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        }
        resp = t.normalize_response(raw)
        assert resp.content == "hello"
        assert resp.finish_reason == "stop"
        assert resp.usage.total_tokens == 15

    def test_normalize_tool_calls(self):
        from butler.transport.chat_completions import ChatCompletionsTransport
        t = ChatCompletionsTransport()
        raw = {
            "choices": [{
                "message": {
                    "content": None,
                    "tool_calls": [{
                        "id": "call_1",
                        "function": {"name": "read_file", "arguments": '{"path": "test.py"}'},
                    }],
                },
                "finish_reason": "tool_calls",
            }],
        }
        resp = t.normalize_response(raw)
        assert resp.tool_calls is not None
        assert len(resp.tool_calls) == 1
        assert resp.tool_calls[0].name == "read_file"
        assert resp.finish_reason == "tool_calls"


class TestAnthropicTransport:
    def test_convert_messages(self):
        from butler.transport.anthropic_transport import _convert_messages_to_anthropic
        msgs = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
        ]
        system, anthropic_msgs = _convert_messages_to_anthropic(msgs)
        assert "helpful" in system
        assert len(anthropic_msgs) == 1
        assert anthropic_msgs[0]["role"] == "user"

    def test_convert_tools(self):
        from butler.transport.anthropic_transport import _convert_tools_to_anthropic
        tools = [{"type": "function", "function": {
            "name": "test", "description": "desc",
            "parameters": {"type": "object", "properties": {}},
        }}]
        result = _convert_tools_to_anthropic(tools)
        assert result[0]["name"] == "test"
        assert "input_schema" in result[0]

    def test_normalize_dict(self):
        from butler.transport.anthropic_transport import AnthropicTransport
        t = AnthropicTransport()
        raw = {
            "content": [{"type": "text", "text": "hello"}],
            "stop_reason": "end_turn",
            "usage": {"input_tokens": 10, "output_tokens": 5},
        }
        resp = t.normalize_response(raw)
        assert resp.content == "hello"
        assert resp.finish_reason == "stop"
        assert resp.usage.total_tokens == 15


class TestProviderRegistry:
    def test_list_providers(self):
        from butler.transport.providers import list_providers
        providers = list_providers()
        assert len(providers) >= 5
        names = {p.name for p in providers}
        assert "deepseek" in names
        assert "minimax" in names

    def test_get_provider(self):
        from butler.transport.providers import get_provider
        p = get_provider("minimax")
        assert p is not None
        assert p.api_mode == "chat_completions"

    def test_alias_resolution(self):
        from butler.transport.providers import get_provider
        p = get_provider("deepseek-chat")
        assert p is not None
        assert p.name == "deepseek"


# ── Agent Loop ──────────────────────────────────────────────

class TestAgentLoop:
    def test_construction(self):
        from butler.core.agent_loop import AgentLoop, LoopConfig
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client, system_prompt="test")
        assert loop.system_prompt == "test"
        assert loop.config.max_iterations == 30

    def test_message_management(self):
        from butler.core.agent_loop import AgentLoop
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client, system_prompt="sys")
        loop.messages = [{"role": "system", "content": "sys"}]
        assert len(loop.messages) == 1
        loop.reset()
        assert len(loop.messages) == 0

    def test_interrupt(self):
        from butler.core.agent_loop import AgentLoop
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client)
        assert not loop._interrupted
        loop.interrupt()
        assert loop._interrupted
        loop.clear_interrupt()
        assert not loop._interrupted


# ── Tool Registry ───────────────────────────────────────────

class TestToolRegistry:
    def test_tool_definitions(self):
        from butler.tools.registry import get_tool_definitions
        tools = get_tool_definitions()
        assert len(tools) >= 7
        names = {t["function"]["name"] for t in tools}
        assert "read_file" in names
        assert "write_file" in names
        assert "terminal" in names
        assert "delegate_task" in names

    def test_dispatch_read_file(self):
        from butler.tools.registry import dispatch_tool
        import tempfile, os
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("line1\nline2\nline3\n")
            path = f.name
        try:
            result = dispatch_tool("read_file", {"path": path})
            assert "line1" in result
            assert "line2" in result
        finally:
            os.unlink(path)

    def test_dispatch_terminal(self):
        from butler.tools.registry import dispatch_tool
        result = dispatch_tool("terminal", {"command": "echo hello"})
        data = json.loads(result)
        assert data["exit_code"] == 0
        assert "hello" in data["output"]

    def test_dispatch_unknown_tool(self):
        from butler.tools.registry import dispatch_tool
        result = dispatch_tool("nonexistent_tool", {})
        data = json.loads(result)
        assert "error" in data

    def test_dispatch_list_directory(self):
        from butler.tools.registry import dispatch_tool
        result = dispatch_tool("list_directory", {"path": "/tmp"})
        data = json.loads(result)
        assert "entries" in data

    def test_dispatch_write_and_patch(self):
        import tempfile, os
        from butler.tools.registry import dispatch_tool
        path = tempfile.mktemp(suffix=".txt")
        try:
            dispatch_tool("write_file", {"path": path, "content": "hello world"})
            assert Path(path).read_text() == "hello world"

            result = dispatch_tool("patch", {"path": path, "old_string": "hello", "new_string": "goodbye"})
            data = json.loads(result)
            assert data["success"]
            assert Path(path).read_text() == "goodbye world"
        finally:
            if os.path.exists(path):
                os.unlink(path)


# ── Orchestrator ────────────────────────────────────────────

class TestOrchestrator:
    def test_build_system_prompt(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        prompt = orch.build_system_prompt()
        assert "delegate_task" in prompt
        assert len(prompt) > 100

    def test_create_llm_client(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        client = orch.create_llm_client("butler")
        assert client.model is not None

    def test_create_agent_loop(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        loop = orch.create_agent_loop(role="butler")
        assert loop is not None
        assert loop.system_prompt

    def test_project_switch_callback(self):
        from butler.orchestrator import ButlerOrchestrator
        orch = ButlerOrchestrator()
        old_router = orch._skill_router
        orch.on_project_switch("old", "new")
        assert orch._skill_router is not None


# ── Task Orchestrator ───────────────────────────────────────

class TestTaskOrchestrator:
    def test_spawn_config_fields(self):
        from butler.task_orchestrator import AgentSpawnConfig
        cfg = AgentSpawnConfig(
            role="dev", task="test",
            tools=["read_file", "terminal"],
            model_config={"provider": "deepseek", "model": "deepseek-chat"},
        )
        assert cfg.tools == ["read_file", "terminal"]
        assert cfg.model_config["provider"] == "deepseek"

    def test_agent_result_fields(self):
        from butler.task_orchestrator import AgentResult
        from butler.report import AgentReport
        report = AgentReport(headline="done", success=True)
        result = AgentResult(
            success=True, response="ok",
            report=report, tokens_used=500,
        )
        assert result.report is not None
        assert result.tokens_used == 500

    def test_topological_sort(self):
        from butler.task_orchestrator import _topological_sort, TaskNode, AgentSpawnConfig
        nodes = [
            TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="t1")),
            TaskNode(id="b", config=AgentSpawnConfig(role="dev", task="t2"), depends_on=["a"]),
            TaskNode(id="c", config=AgentSpawnConfig(role="dev", task="t3"), depends_on=["a"]),
            TaskNode(id="d", config=AgentSpawnConfig(role="dev", task="t4"), depends_on=["b", "c"]),
        ]
        order = _topological_sort(nodes)
        assert order[0] == "a"
        assert order[-1] == "d"

    def test_cycle_detection(self):
        from butler.task_orchestrator import _topological_sort, TaskNode, AgentSpawnConfig
        nodes = [
            TaskNode(id="x", config=AgentSpawnConfig(role="dev", task="t1"), depends_on=["y"]),
            TaskNode(id="y", config=AgentSpawnConfig(role="dev", task="t2"), depends_on=["x"]),
        ]
        with pytest.raises(ValueError, match="cycle"):
            _topological_sort(nodes)

    def test_layer_grouping(self):
        from butler.task_orchestrator import _topological_sort, _group_into_layers, TaskNode, AgentSpawnConfig
        nodes = [
            TaskNode(id="a", config=AgentSpawnConfig(role="dev", task="t1")),
            TaskNode(id="b", config=AgentSpawnConfig(role="dev", task="t2")),
            TaskNode(id="c", config=AgentSpawnConfig(role="dev", task="t3"), depends_on=["a", "b"]),
        ]
        order = _topological_sort(nodes)
        node_map = {n.id: n for n in nodes}
        layers = _group_into_layers(order, node_map)
        assert len(layers) == 2
        assert set(layers[0]) == {"a", "b"}
        assert layers[1] == ["c"]


# ── Report ──────────────────────────────────────────────────

class TestReport:
    def test_agent_report_new_fields(self):
        from butler.report import AgentReport
        r = AgentReport(
            headline="test", success=True,
            iterations=5, tool_calls=3, tokens_used=1000,
        )
        assert r.success is True
        assert r.tokens_used == 1000

    def test_cache_mechanism(self):
        from butler.report import AgentReport, cache_report, get_last_report
        r = AgentReport(headline="cached_test")
        cache_report(r)
        assert get_last_report() is r

    def test_format_for_cli(self):
        from butler.report import AgentReport, Change, format_for_cli
        r = AgentReport(
            headline="完成任务",
            changes=[Change(file="test.py", action="modified", description="修改了函数")],
        )
        result = format_for_cli(r)
        assert "完成任务" in result
        assert "test.py" in result


# ── Gateway Message Handler ─────────────────────────────────

class TestGatewayHandler:
    def test_command_projects(self):
        from butler.gateway.message_handler import ButlerMessageHandler
        handler = ButlerMessageHandler(channel="test")
        result = handler._handle_command("/projects")
        assert result is not None

    def test_command_status(self):
        from butler.gateway.message_handler import ButlerMessageHandler
        handler = ButlerMessageHandler(channel="test")
        result = handler._handle_command("/status")
        assert "Butler" in result

    def test_command_model_view(self):
        from butler.gateway.message_handler import ButlerMessageHandler
        handler = ButlerMessageHandler(channel="test")
        result = handler._handle_command("/model")
        assert "butler" in result.lower()

    def test_non_command_returns_none(self):
        from butler.gateway.message_handler import ButlerMessageHandler
        handler = ButlerMessageHandler(channel="test")
        assert handler._handle_command("hello") is None

    def test_command_new(self):
        from butler.gateway.message_handler import ButlerMessageHandler
        handler = ButlerMessageHandler(channel="test")
        result = handler._handle_command("/new")
        assert "清空" in result


# ── Agent Profiles ──────────────────────────────────────────

class TestAgentProfiles:
    def test_dev_profile(self):
        from butler.agent_profiles import get_profile
        p = get_profile("dev")
        assert p is not None
        assert p.role == "dev_agent"
        assert "code_editing" in p.toolsets

    def test_model_aware_prompt(self):
        from butler.agent_profiles import get_model_aware_prompt_extra
        extra = get_model_aware_prompt_extra("deepseek")
        assert extra
        assert "function calling" in extra


# ── Main CLI ────────────────────────────────────────────────

class TestAgentLoopContextCompression:
    def test_estimate_tokens(self):
        from butler.core.agent_loop import AgentLoop
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client)
        msgs = [{"role": "user", "content": "a" * 400}]
        assert loop._estimate_tokens(msgs) == 100

    def test_compress_short_context(self):
        from butler.core.agent_loop import AgentLoop, LoopConfig
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client, config=LoopConfig(max_context_tokens=10000))
        msgs = [{"role": "user", "content": "hello"}]
        assert loop._compress_context(msgs) == msgs

    def test_compress_long_context(self):
        from butler.core.agent_loop import AgentLoop, LoopConfig
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client, config=LoopConfig(max_context_tokens=50))
        msgs = [
            {"role": "system", "content": "sys"},
        ] + [
            {"role": "user", "content": "x" * 200}
            for _ in range(20)
        ]
        from butler.core.context_compressor import SUMMARY_PREFIX
        compressed = loop._compress_context(msgs)
        assert compressed[0]["role"] == "system"
        assert len(compressed) < len(msgs) or any(
            SUMMARY_PREFIX[:20] in str(m.get("content", "")) for m in compressed
        )


class TestE2EToolFlow:
    """Simulate a full AgentLoop turn with mocked LLM."""

    def test_tool_call_flow(self):
        from butler.core.agent_loop import AgentLoop, LoopConfig, LoopCallbacks
        from butler.transport.llm_client import LLMClient
        from butler.transport.types import NormalizedResponse, ToolCall

        client = LLMClient(provider="minimax", model="test")
        call_count = {"n": 0}

        def mock_complete(messages, tools=None, **kw):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return NormalizedResponse(
                    content=None,
                    tool_calls=[ToolCall(id="c1", name="terminal", arguments='{"command": "echo ok"}')],
                    finish_reason="tool_calls",
                )
            return NormalizedResponse(content="Done!", finish_reason="stop")

        client.complete = mock_complete

        tools = [{"type": "function", "function": {"name": "terminal", "description": "run", "parameters": {}}}]

        def dispatcher(name, args):
            return '{"exit_code": 0, "output": "ok"}'

        loop = AgentLoop(
            client=client,
            system_prompt="test",
            tools=tools,
            tool_dispatcher=dispatcher,
            config=LoopConfig(stream=False),
        )

        result = loop.run("run echo ok")
        assert result.final_response == "Done!"
        assert result.tool_calls_made == 1
        assert result.iterations == 2

    def test_loop_error_recovery(self):
        from butler.core.agent_loop import AgentLoop, LoopConfig, LoopStatus
        from butler.transport.llm_client import LLMClient

        client = LLMClient(provider="minimax", model="test")
        client.complete = MagicMock(side_effect=Exception("API down"))

        loop = AgentLoop(
            client=client,
            config=LoopConfig(stream=False, max_retries=2, retry_delay=0),
        )
        result = loop.run("test")
        assert result.status == LoopStatus.ERROR


class TestMainCLI:
    def test_handle_help(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/help", orch, console)
        assert result == "handled"

    def test_handle_quit(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/quit", orch, console)
        assert result == "quit"

    def test_handle_detail(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/detail", orch, console)
        assert result == "handled"

    def test_handle_status(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/status", orch, console)
        assert result == "handled"
        console.print.assert_called()

    def test_no_hermes_import(self):
        """Verify main.py does not import from run_agent."""
        import butler.main as main_mod
        import inspect
        source = inspect.getsource(main_mod)
        assert "from run_agent import" not in source
        assert "import AIAgent" not in source

    def test_unknown_command(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/nonexistent", orch, console)
        assert result is None


class TestTransportAnthropicEdgeCases:
    def test_tool_result_conversion(self):
        from butler.transport.anthropic_transport import _convert_messages_to_anthropic
        msgs = [
            {"role": "system", "content": "sys"},
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": None, "tool_calls": [
                {"id": "t1", "function": {"name": "test", "arguments": '{"a": 1}'}},
            ]},
            {"role": "tool", "tool_call_id": "t1", "content": "result"},
        ]
        system, anthropic_msgs = _convert_messages_to_anthropic(msgs)
        assert system == "sys"
        assert len(anthropic_msgs) == 3
        assert anthropic_msgs[2]["content"][0]["type"] == "tool_result"

    def test_empty_content_handling(self):
        from butler.transport.anthropic_transport import AnthropicTransport
        t = AnthropicTransport()
        raw = {"content": [], "stop_reason": "end_turn"}
        resp = t.normalize_response(raw)
        assert resp.content is None
        assert resp.finish_reason == "stop"


class TestProviderProfileResolve:
    def test_api_key_from_env(self):
        import os
        from butler.transport.providers import ProviderProfile
        os.environ["TEST_BUTLER_KEY_12345"] = "sk-test"
        try:
            p = ProviderProfile(name="test", env_vars=("TEST_BUTLER_KEY_12345",))
            assert p.resolve_api_key() == "sk-test"
        finally:
            del os.environ["TEST_BUTLER_KEY_12345"]

    def test_no_key(self):
        from butler.transport.providers import ProviderProfile
        p = ProviderProfile(name="nokey", env_vars=("NONEXISTENT_KEY_XYZ",))
        assert p.resolve_api_key() is None
