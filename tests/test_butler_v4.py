"""Butler v4 integration tests — orchestrator, loop E2E, CLI (no transport duplicates).

Transport/providers/gateway/task_orchestrator coverage lives in dedicated test_*.py modules.
"""

import json
import pytest
from unittest.mock import MagicMock, patch


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
        orch.on_project_switch("old", "new")
        assert orch._skill_router is not None


class TestAgentLoopContextCompression:
    def test_estimate_tokens(self):
        from butler.core.agent_loop import AgentLoop
        from butler.transport.llm_client import LLMClient
        client = LLMClient(provider="minimax", model="test")
        loop = AgentLoop(client=client)
        msgs = [{"role": "user", "content": "a" * 400}]
        assert loop._estimate_tokens(msgs) >= 100

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
        with patch(
            "butler.core.context_compress_support.auxiliary_summarize_middle",
            return_value="## Active Task\n- compressed summary",
        ):
            compressed = loop._compress_context(msgs)
        assert compressed[0]["role"] == "system"
        assert len(compressed) < len(msgs) or any(
            SUMMARY_PREFIX[:20] in str(m.get("content", "")) for m in compressed
        )


class TestE2EToolFlow:
    """Simulate a full AgentLoop turn with mocked LLM."""

    def test_tool_call_flow(self):
        from butler.core.agent_loop import AgentLoop, LoopConfig
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
        client.complete = MagicMock(side_effect=Exception("API down"))  # noqa: magicmock-no-spec — complex facade, spec= 收益低

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
        console = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/help", orch, console)
        assert result == "handled"

    def test_handle_quit(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/quit", orch, console)
        assert result == "quit"

    def test_handle_detail(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/detail", orch, console)
        assert result == "handled"

    def test_handle_status(self):
        from butler.main import _handle_slash_command
        from butler.orchestrator import ButlerOrchestrator
        console = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
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
        console = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        orch = ButlerOrchestrator()
        result = _handle_slash_command("/nonexistent", orch, console)
        assert result is None
