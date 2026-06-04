"""L4 end-to-end tests — full Butler pipeline with only the LLM boundary mocked."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from butler.core.agent_loop import LoopConfig, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.tools.registry import dispatch_tool, get_tool_definitions
from butler.transport.types import NormalizedResponse, Usage, build_tool_call

LLM_PATCH = "butler.transport.llm_client.LLMClient"


def _text_response(content: str) -> NormalizedResponse:
    return NormalizedResponse(
        content=content,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _tool_response(name: str, args: dict, *, tool_id: str = "call_1") -> NormalizedResponse:
    return NormalizedResponse(
        tool_calls=[build_tool_call(tool_id, name, args)],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.fixture
def patch_llm(mock_llm_response):
    """Patch LLMClient.complete and .stream at the HTTP boundary."""
    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        default = mock_llm_response()
        mock_complete.return_value = default
        mock_stream.return_value = default
        yield mock_complete, mock_stream


@pytest.mark.e2e
class TestCLIE2E:
    def test_simple_conversation(self, butler_orchestrator, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="你好，我是 Butler。")
        mock_stream.return_value = mock_complete.return_value

        loop = butler_orchestrator.create_agent_loop(role="butler")
        loop.config = LoopConfig(stream=False)
        result = loop.run("你好")

        assert result.status == LoopStatus.COMPLETED
        assert result.final_response
        assert len(result.final_response) > 0
        mock_complete.assert_called()

    def test_tool_call_flow(self, butler_orchestrator, patch_llm, tmp_path, monkeypatch):
        mock_complete, _mock_stream = patch_llm
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))
        tmp_file = tmp_path / "e2e_read.txt"
        tmp_file.write_text("hello from e2e\nsecond line\n", encoding="utf-8")

        mock_complete.side_effect = [
            _tool_response("read_file", {"path": str(tmp_file)}),
            _text_response("File contents reviewed."),
        ]

        loop = butler_orchestrator.create_agent_loop(
            role="butler",
            tools=get_tool_definitions(),
            tool_dispatcher=dispatch_tool,
        )
        loop.config = LoopConfig(stream=False)
        result = loop.run("read the file")

        assert result.status == LoopStatus.COMPLETED
        assert result.iterations == 2
        assert result.tool_calls_made == 1
        assert result.final_response == "File contents reviewed."
        assert any(
            msg.get("role") == "tool" and "hello from e2e" in str(msg.get("content"))
            for msg in result.messages
        )

    def test_multi_turn_context(self, butler_orchestrator, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            mock_llm_response(content="first reply"),
            mock_llm_response(content="second reply"),
        ]
        mock_stream.side_effect = mock_complete.side_effect

        loop = butler_orchestrator.create_agent_loop(role="butler")
        loop.config = LoopConfig(stream=False)

        loop.run("first message")
        assert len(loop.messages) >= 3  # system + user + assistant

        loop.run("second message")
        msgs = loop.messages
        roles = [m["role"] for m in msgs]
        assert roles.count("user") == 2
        assert roles.count("assistant") == 2
        assert len(msgs) >= 5  # system + user1 + asst1 + user2 + asst2

        loop.reset()
        assert loop.messages == []


@pytest.mark.e2e
class TestGatewayE2E:
    def test_gateway_simple_message(self, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="网关回复内容")
        mock_stream.return_value = mock_complete.return_value

        handler = ButlerMessageHandler(channel="test")
        response = handler.handle_message("你好")

        assert response
        assert len(response) > 0
        assert "网关回复内容" in response

    def test_gateway_slash_commands(self, butler_orchestrator):
        handler = ButlerMessageHandler(channel="test")
        handler._orchestrator = butler_orchestrator

        status = handler.handle_message("/status")
        assert "Butler" in status

        cleared = handler.handle_message("/new")
        assert "已清空本轮对话上下文" in cleared

        model_info = handler.handle_message("/model")
        assert "butler" in model_info or "模型" in model_info

    def test_gateway_session_isolation(self, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="ok")
        mock_stream.return_value = mock_complete.return_value

        handler = ButlerMessageHandler(channel="test")
        handler.handle_message("msg1", session_key="s1")
        handler.handle_message("msg2", session_key="s2")

        assert "s1" in handler._sessions
        assert "s2" in handler._sessions
        assert handler._sessions["s1"] is not handler._sessions["s2"]


@pytest.mark.e2e
class TestDelegateE2E:
    def test_delegate_task_tool(self, mock_llm_response):
        from butler.core.agent_loop import LoopResult

        mock_agent = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_agent.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="test task output from dev agent",
            iterations=1,
            tool_calls_made=0,
            total_tokens=50,
            elapsed_seconds=0.5,
        )
        mock_orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_orch.create_project_agent_loop.return_value = mock_agent

        with patch("butler.orchestrator.ButlerOrchestrator", return_value=mock_orch):
            result = dispatch_tool(
                "delegate_task",
                {"task": "test task", "role": "dev"},
            )

        data = json.loads(result)
        assert data["success"] is True
        assert "test task output" in data["summary"]
        mock_orch.create_project_agent_loop.assert_called_once()
        call_kwargs = mock_orch.create_project_agent_loop.call_args
        assert call_kwargs[1].get("role") == "dev" or call_kwargs[0][0] == "dev"

    def test_report_caching(self, mock_llm_response):
        from butler import report as report_mod
        from butler.core.agent_loop import LoopResult

        report_mod._last_report = None

        mock_agent = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_agent.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="cached delegation summary",
            iterations=2,
            tool_calls_made=1,
            total_tokens=120,
            elapsed_seconds=1.0,
        )
        mock_orch = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
        mock_orch.create_project_agent_loop.return_value = mock_agent

        with patch("butler.orchestrator.ButlerOrchestrator", return_value=mock_orch):
            dispatch_tool("delegate_task", {"task": "cache me", "role": "dev"})

        from butler.report import get_last_report

        report = get_last_report()
        assert report is not None
        assert "cached delegation summary" in report.summary
        assert report.success is True
