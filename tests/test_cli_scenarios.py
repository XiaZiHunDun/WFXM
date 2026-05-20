"""CLI real-scenario TDD tests — regressions from manual chat sessions.

Maps to docs/guides/manual-testing-guide.md §二, focused on display,
streaming buffer, /new post-session, and scripted interactive flows.
"""

from __future__ import annotations

from io import StringIO
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.patch_stdout import patch_stdout
from rich.panel import Panel

from butler.cli.session_ui import ChatSessionUI
from butler.cli.stream import StreamRenderer
from butler.main import _handle_slash_command, _run_interactive_chat
from butler.session_lifecycle import trigger_session_end
from tests.cli_harness import (
    assert_no_ansi_artifacts,
    capture_console,
    count_substring,
    finish_turn_capture,
    make_loop_result,
    mock_orchestrator_for_chat,
    panels_from_console,
    rendered_text,
    run_scripted_interactive_chat,
)


@pytest.mark.module_test
class TestStreamRendererBufferOnly:
    """Buffer mode: deltas accumulate until finish_turn Panel."""

    def test_buffer_mode_does_not_print_during_delta(self):
        console = MagicMock()
        stream = StreamRenderer(console, title="莎丽", mode="buffer")
        stream.on_delta("你好")
        stream.on_delta("世界")
        console.print.assert_not_called()
        assert stream.text == "你好世界"

    def test_thinking_tag_markers_stripped_from_buffer(self):
        stream = StreamRenderer(mode="buffer")
        stream.on_delta("</think>可见")
        assert "</think>" not in stream.text
        assert "可见" in stream.text

    def test_empty_delta_ignored(self):
        stream = StreamRenderer(mode="buffer")
        stream.on_delta("")
        stream.on_delta(None)
        assert stream.text == ""


@pytest.mark.module_test
class TestFinishTurnDisplayRegression:
    """Regressions: duplicate output, empty panel border, missing body, ANSI garbage."""

    def test_panel_shows_stream_buffer_once(self):
        out = finish_turn_capture(
            stream_chunks=["你好！", "有什么我可以帮你的吗？"],
            final_response="你好！有什么我可以帮你的吗？",
        )
        assert "你好！" in out
        assert "有什么我可以帮你的吗？" in out
        assert_no_ansi_artifacts(out)

    def test_no_duplicate_panel_for_same_content(self):
        text = "你好！我是莎丽。"
        out = finish_turn_capture(
            stream_chunks=list(text),
            final_response=text,
        )
        assert count_substring(out, text) == 1

    def test_final_response_used_when_stream_empty(self):
        """Regression: stream buffer empty but model returned final_response."""
        out = finish_turn_capture(
            stream_chunks=[],
            final_response="你叫测试员。",
        )
        assert "你叫测试员" in out
        assert_no_ansi_artifacts(out)

    def test_empty_turn_prints_no_assistant_panel(self):
        out = finish_turn_capture(stream_chunks=[], final_response="")
        assert "莎丽" not in out  # no titled assistant panel
        assert out.strip() == ""

    def test_reasoning_hidden_by_default(self):
        out = finish_turn_capture(
            stream_chunks=["回复"],
            final_response="回复",
            reasoning="internal chain-of-thought",
        )
        assert "推理:" not in out
        assert "internal chain" not in out

    def test_reasoning_shown_when_env_enabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_CLI_SHOW_REASONING", "1")
        out = finish_turn_capture(
            stream_chunks=["回复"],
            final_response="回复",
            reasoning="visible reasoning snippet",
        )
        assert "推理:" in out
        assert "visible reasoning" in out

    def test_finish_turn_single_panel_via_mock_console(self):
        console = MagicMock()
        ui = ChatSessionUI(console, stream_title="莎丽")
        stream = StreamRenderer(console, title="莎丽", mode="buffer")
        stream.on_delta("Panel 正文")
        ui.finish_turn(
            make_loop_result("Panel 正文"),
            stream,
        )
        from rich.markdown import Markdown

        panels = panels_from_console(console, console.print.call_args_list)
        assert len(panels) == 1
        assert isinstance(panels[0].renderable, Markdown)


@pytest.mark.module_test
class TestPatchStdoutLayout:
    """Regression: live stream + Rich status work with stderr console."""

    def test_llm_start_uses_rich_status(self):
        console = MagicMock()
        status = MagicMock()
        console.status.return_value = status
        ui = ChatSessionUI(console)
        ui._on_llm_start()
        console.status.assert_called_once()
        status.start.assert_called_once()

    def test_finish_turn_outside_patch_stdout_is_visible(self):
        console, buf = capture_console()
        ui = ChatSessionUI(console, stream_title="莎丽")
        stream = StreamRenderer(console, title="莎丽", mode="live")

        with patch_stdout():
            stream.on_delta("缓冲期\n")

        stream.flush()
        ui.finish_turn(make_loop_result("缓冲期"), stream)
        out = rendered_text(buf)
        assert "缓冲期" in out

    def test_stream_buffer_survives_patch_stdout(self):
        stream = StreamRenderer(title="莎丽")
        with patch_stdout():
            stream.on_delta("你好")
            stream.on_delta("莎丽")
        assert stream.text == "你好莎丽"


@pytest.mark.integration
class TestScriptedInteractiveChat:
    """End-to-end scripted CLI flows mirroring manual §2.2 / §2.3.6 sessions."""

    def test_greeting_identity_and_new_without_extraction_errors(self, tmp_path):
        orch = mock_orchestrator_for_chat(
            tmp_path,
            responses={
                "你好": make_loop_result("你好！有什么我可以帮你的吗？"),
                "我叫测试员": make_loop_result(
                    "你好，测试员！很高兴认识你。我是莎丽，你的 AI 管家。"
                ),
                "我叫什么": make_loop_result("你叫测试员。"),
            },
        )

        with patch(
            "butler.transport.auxiliary_client.auxiliary_complete",
            return_value='{"updates": []}',
        ):
            run = run_scripted_interactive_chat(
                orch,
                ["你好", "我叫测试员", "我叫什么", "/new", "/quit"],
            )
            out = run.output

        assert run.exit_code == 0
        assert "Butler v4" in out or "Butler AI" in out
        assert "你好" in out
        assert "测试员" in out
        assert "已清空对话历史" in out
        assert "Memory extraction failed" not in out
        assert "Skill extraction failed" not in out
        assert "can't be used in 'await'" not in out
        assert_no_ansi_artifacts(out)

    def test_new_triggers_post_session_with_async_llm(self, tmp_path):
        orch = mock_orchestrator_for_chat(
            tmp_path,
            responses={"你好": make_loop_result("hi")},
        )
        loop = orch.create_agent_loop()
        # Ensure long enough history
        assert len(loop.messages) > 4

        with patch(
            "butler.transport.auxiliary_client.auxiliary_complete",
            return_value='{"updates": []}',
        ) as aux:
            result = trigger_session_end(orch, loop)

        assert result.get("errors", []) == []
        assert aux.called

    def test_slash_new_rebuilds_agent_loop(self, tmp_path):
        orch = mock_orchestrator_for_chat(
            tmp_path,
            responses={"ping": make_loop_result("pong")},
        )
        run_scripted_interactive_chat(orch, ["ping", "/new", "ping", "/quit"])
        assert orch.create_agent_loop.call_count >= 2  # initial + /new


@pytest.mark.integration
class TestCliScenarioSlashCommands:
    def test_new_prints_cleared_message(self):
        console, buf = capture_console()
        orch = MagicMock()
        assert _handle_slash_command("/new", orch, console) == "rebuild"
        assert "已清空对话历史" in rendered_text(buf)


@pytest.mark.integration
class TestCliMultiTurnMemorySemantics:
    """§2.3.6: loop reset vs memory layer (orchestrator-level, not display)."""

    def test_agent_loop_reset_clears_messages(self, butler_orchestrator, mock_llm_response):
        from butler.core.agent_loop import LoopConfig
        from butler.transport.types import NormalizedResponse, Usage

        LLM_PATCH = "butler.transport.llm_client.LLMClient"

        def _resp(text: str):
            return NormalizedResponse(
                content=text,
                usage=Usage(prompt_tokens=1, completion_tokens=1, total_tokens=2),
            )

        with (
            patch(f"{LLM_PATCH}.complete") as mock_complete,
            patch(f"{LLM_PATCH}.stream") as mock_stream,
        ):
            mock_complete.side_effect = [_resp("记住李四"), _resp("你叫李四。")]
            mock_stream.side_effect = lambda *a, **k: mock_complete.side_effect[
                mock_complete.call_count - 1
            ]

            loop = butler_orchestrator.create_agent_loop(role="butler")
            loop.config = LoopConfig(stream=False)
            with patch(
                "butler.session_lifecycle.sync_turn_memory",
                return_value={"skipped": True},
            ):
                loop.run("我叫李四")
                assert len(loop.messages) >= 3
                loop.reset()
                assert loop.messages == []
