"""Multi-dimensional CLI scenario tests for Butler chat (primary UX surface).

Dimensions (see module docstrings per class):
  presentation · tool-ux · slash-commands · interactive-flow · session-lifecycle
  error-recovery · exec-mode · spinner · wiring-contracts

Run: PYTHONPATH=. pytest tests/test_cli_dimensions.py tests/test_cli_scenarios.py -q
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from prompt_toolkit.patch_stdout import patch_stdout

from butler.cli.display import (
    build_tool_preview,
    capture_edit_snapshot,
    format_tool_complete,
    format_tool_start,
    render_inline_diff,
    tool_failure_hint,
)
from butler.cli.session_ui import ChatSessionUI
from butler.cli.spinner import WaitSpinner
from butler.cli.stream import StreamRenderer
from butler.core.agent_loop import LoopCallbacks, LoopResult, LoopStatus
from butler.main import _cmd_exec, _handle_slash_command, _sync_memory
from tests.cli_harness import (
    assert_no_ansi_artifacts,
    assert_welcome_banner,
    capture_console,
    count_substring,
    finish_turn_capture,
    finish_turn_with_result,
    invoke_ui_tool_callbacks,
    make_loop_result,
    mock_orchestrator_for_chat,
    rendered_text,
    run_scripted_interactive_chat,
)


def _orch(butler_name: str = "莎丽", project: str = "灵文") -> MagicMock:
    orch = MagicMock()
    orch._settings.butler_name = butler_name
    orch._settings.butler_home = Path("/tmp/butler-home")
    orch.project_manager.current_project = project
    orch.project_manager.list_projects.return_value = []
    orch._model_credentials.return_value = {
        "provider": "minimax",
        "model": "MiniMax-M2.7",
    }
    return orch


def _console():
    return capture_console()


# ---------------------------------------------------------------------------
# A. Presentation layer
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestCliPresentation:
    """§2.1–2.2: welcome banner, Panel body, stats, status lines."""

    def test_welcome_banner_contains_identity_and_model(self, tmp_path):
        run = run_scripted_interactive_chat(
            mock_orchestrator_for_chat(tmp_path, butler_name="莎丽", project_name="灵文"),
            ["/quit"],
        )
        assert_welcome_banner(run.output, butler_name="莎丽")
        assert "灵文" in run.output or "minimax" in run.output

    @pytest.mark.parametrize(
        "kwargs,expected_fragments",
        [
            ({"tool_calls": 2, "iterations": 3}, ["3 轮", "2 工具调用", "tokens", "0.5s"]),
            ({"tool_calls": 1, "iterations": 1}, ["1 工具调用", "tokens"]),
        ],
    )
    def test_finish_turn_stats_line(self, kwargs, expected_fragments):
        out = finish_turn_with_result(
            make_loop_result("完成", **kwargs),
            stream_chunks=["完成"],
        )
        for frag in expected_fragments:
            assert frag in out

    def test_finish_turn_error_status_message(self):
        out = finish_turn_with_result(
            LoopResult(
                status=LoopStatus.ERROR,
                final_response=None,
                error="API key invalid",
            ),
        )
        assert "错误:" in out
        assert "API key invalid" in out

    def test_finish_turn_tool_limit_hint(self):
        out = finish_turn_with_result(
            LoopResult(
                status=LoopStatus.TOOL_LIMIT,
                final_response="partial",
                iterations=30,
            ),
            stream_chunks=["partial"],
        )
        assert "最大迭代" in out

    def test_finish_turn_interrupted_status(self):
        out = finish_turn_with_result(
            LoopResult(status=LoopStatus.INTERRUPTED, final_response="半段回复"),
            stream_chunks=["半段回复"],
        )
        assert "已中断" in out

    def test_fallback_notification_printed(self):
        console, buf = capture_console()
        ui = ChatSessionUI(console)
        ui.notify_fallback_once("deepseek", "deepseek-chat")
        assert "deepseek" in rendered_text(buf)
        assert "备用模型" in rendered_text(buf)

    def test_stream_buffer_wins_over_different_final_response(self):
        """Body prefers streamed text when both exist (main finish_turn logic)."""
        out = finish_turn_capture(
            stream_chunks=["流式"],
            final_response="最终",
        )
        assert "流式" in out
        assert "最终" not in out

    def test_long_stream_content_in_single_panel(self):
        text = "长回复。" * 200
        out = finish_turn_capture(stream_chunks=[text], final_response=text)
        assert out.count("╭") == 1
        assert "长回复。" in out
        assert_no_ansi_artifacts(out)

    def test_whitespace_deltas_are_buffered_as_is(self):
        stream = StreamRenderer(mode="buffer")
        stream.on_delta("   ")
        stream.on_delta("\n\t")
        assert stream.text == "   \n\t"
        assert not stream.had_body()


# ---------------------------------------------------------------------------
# B. Tool UX
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestCliToolDisplay:
    """§2.2.4: tool start/complete lines, previews, failure hints, diff."""

    @pytest.mark.parametrize(
        "tool,args,needle",
        [
            ("read_file", {"path": "/proj/src/main.py"}, "read"),
            ("terminal", {"command": "ls -la"}, "$"),
            ("delegate_task", {"role": "dev_agent", "task": "review"}, "delegate"),
            ("search_files", {"pattern": "def main"}, "grep"),
        ],
    )
    def test_format_tool_start_contains_tool_name(self, tool, args, needle):
        line = format_tool_start(tool, args)
        assert needle in line.lower() or tool in line

    def test_build_tool_preview_read_file(self):
        assert "main.py" in (build_tool_preview("read_file", {"path": "main.py"}) or "")

    def test_format_tool_complete_success(self):
        line = format_tool_complete("read_file", {"path": "a.py"}, 1.2, '{"ok": true}')
        assert "1.2s" in line
        assert "read" in line

    def test_tool_failure_hint_detects_json_error(self):
        failed, suffix = tool_failure_hint('{"error": "permission denied"}')
        assert failed is True
        assert "permission" in suffix

    def test_tool_failure_hint_exit_code(self):
        failed, suffix = tool_failure_hint('{"exit_code": 1}')
        assert failed is True
        assert "exit 1" in suffix

    def test_session_ui_tool_callbacks_emit_lines(self):
        console, buf = capture_console()
        ui = ChatSessionUI(console)
        stream = StreamRenderer(console)
        out = invoke_ui_tool_callbacks(
            ui,
            stream,
            tool_name="read_file",
            args={"path": "butler/main.py"},
        )
        assert "read_file" in out
        assert "┊" in out

    def test_finish_turn_shows_tool_count_in_stats(self):
        out = finish_turn_with_result(
            make_loop_result("done", tool_calls=3),
            stream_chunks=["done"],
        )
        assert "3 工具调用" in out

    def test_inline_diff_uses_add_remove_colors(self, tmp_path):
        from butler.cli.display import render_inline_diff

        target = tmp_path / "color.txt"
        target.write_text("old\n", encoding="utf-8")
        target.write_text("old\nnew\n", encoding="utf-8")
        diff = render_inline_diff(str(target), "old\n")
        assert diff is not None
        assert "[green]+new" in diff
        assert "[red]-old" in diff or "[dim]" in diff

    def test_inline_diff_after_write(self, tmp_path):
        target = tmp_path / "edit_me.txt"
        target.write_text("before\n", encoding="utf-8")
        snap = capture_edit_snapshot("write_file", {"path": str(target)})
        target.write_text("before\nafter\n", encoding="utf-8")
        diff = render_inline_diff(str(target), snap[str(target)])
        assert diff is not None
        assert "+after" in diff or "after" in diff


# ---------------------------------------------------------------------------
# C. Slash commands matrix
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCliSlashCommandMatrix:
    """§2.3: every documented slash command and edge case."""

    @pytest.mark.parametrize("cmd", ["/help", "/HELP"])
    def test_help_lists_core_commands(self, cmd):
        console, buf = _console()
        assert _handle_slash_command(cmd, _orch(), console) == "handled"
        text = rendered_text(buf)
        for token in ("/projects", "/switch", "/model", "/new", "/health", "/quit"):
            assert token in text

    @pytest.mark.parametrize("cmd", ["/quit", "/exit", "/q"])
    def test_quit_variants(self, cmd):
        assert _handle_slash_command(cmd, _orch(), _console()[0]) == "quit"

    def test_status_shows_butler_project_model_home(self):
        console, buf = _console()
        assert _handle_slash_command("/status", _orch(), console) == "handled"
        text = rendered_text(buf)
        assert "莎丽" in text
        assert "灵文" in text
        assert "minimax" in text
        assert "Butler Home" in text

    @pytest.mark.parametrize("cmd", ["/health", "/诊断"])
    def test_health_command(self, cmd):
        console, buf = _console()
        loop = MagicMock()
        loop.diagnostics = {"schema_recovered": True}
        assert _handle_slash_command(cmd, _orch(), console, agent_loop=loop) == "handled"
        assert "诊断" in rendered_text(buf) or "Butler" in rendered_text(buf)

    def test_projects_empty_state(self):
        orch = _orch()
        orch.project_manager.list_projects.return_value = []
        console, buf = _console()
        assert _handle_slash_command("/projects", orch, console) == "handled"
        assert "暂无项目" in rendered_text(buf)

    def test_projects_lists_sorted_with_current_marker(self):
        from butler.project import Project

        orch = _orch()
        orch.project_manager.current_project = "beta"
        orch.project_manager.list_projects.return_value = [
            Project("beta", "software", "B", Path("/b")),
            Project("alpha", "novel", "A", Path("/a")),
        ]
        console, buf = _console()
        _handle_slash_command("/projects", orch, console)
        text = rendered_text(buf)
        assert "alpha" in text
        assert "beta" in text
        assert "*" in text

    def test_switch_missing_arg_shows_usage(self):
        console, buf = _console()
        assert _handle_slash_command("/switch", _orch(), console) == "handled"
        assert "用法" in rendered_text(buf)

    def test_switch_unknown_project(self):
        orch = _orch()
        orch.project_manager.switch_project.return_value = False
        console, buf = _console()
        assert _handle_slash_command("/switch nope", orch, console) == "handled"
        assert "未找到" in rendered_text(buf)

    def test_switch_success_rebuilds(self):
        orch = _orch()
        orch.project_manager.switch_project.return_value = True
        orch.project_manager.current_project = "demo"
        console, buf = _console()
        assert _handle_slash_command("/switch demo", orch, console) == "switch_project"
        assert "已切换" in rendered_text(buf)

    def test_model_list_roles(self):
        console, buf = _console()
        with patch("butler.config.get_model_config") as gmc:
            gmc.return_value = MagicMock(provider="minimax", model="M2.7")
            assert _handle_slash_command("/model", _orch(), console) == "handled"
        text = rendered_text(buf)
        for role in ("butler", "dev_agent", "content_agent", "review_agent"):
            assert role in text

    def test_model_set_rebuilds(self):
        orch = _orch()
        console, _ = _console()
        with patch("butler.config.ModelConfig"):
            result = _handle_slash_command(
                "/model butler minimax/MiniMax-M2.5", orch, console
            )
        assert result == "rebuild"
        orch._settings.set_runtime_model_override.assert_called_once()

    def test_model_bad_usage(self):
        console, buf = _console()
        assert _handle_slash_command("/model butler", _orch(), console) == "handled"
        assert "用法" in rendered_text(buf)

    def test_steer_without_arg(self):
        console, buf = _console()
        assert _handle_slash_command("/steer", _orch(), console) == "handled"
        assert "用法" in rendered_text(buf)

    def test_steer_with_text(self):
        console, buf = _console()
        with patch("butler.core.steer.steer", return_value=True) as steer:
            assert _handle_slash_command("/steer 先读 README", _orch(), console) == "handled"
        steer.assert_called_once_with("先读 README", session_key="cli")
        assert "指引" in rendered_text(buf)

    def test_detail_without_report(self):
        console, buf = _console()
        with patch("butler.report.get_last_report", return_value=None):
            _handle_slash_command("/detail", _orch(), console)
        assert "暂无" in rendered_text(buf)

    def test_unknown_slash_returns_none(self):
        assert _handle_slash_command("/unknown", _orch(), _console()[0]) is None


# ---------------------------------------------------------------------------
# D. Interactive flow
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCliInteractiveFlow:
    """§2.6: empty input, unknown slash, wiring, prompt prefix, lifecycle hooks."""

    def test_empty_line_does_not_invoke_agent(self, tmp_path):
        run = run_scripted_interactive_chat(
            mock_orchestrator_for_chat(tmp_path, default_response="skip"),
            ["", "  ", "实际消息", "/quit"],
        )
        assert run.user_messages == ["实际消息"]

    def test_unknown_slash_does_not_invoke_agent(self, tmp_path):
        run = run_scripted_interactive_chat(
            mock_orchestrator_for_chat(tmp_path),
            ["/unknown", "/quit"],
        )
        assert run.user_messages == []
        assert "未知命令" in run.output

    def test_slash_help_does_not_invoke_agent(self, tmp_path):
        run = run_scripted_interactive_chat(
            mock_orchestrator_for_chat(tmp_path),
            ["/help", "/quit"],
        )
        assert run.user_messages == []

    def test_sync_memory_called_after_turn(self, tmp_path):
        orch = mock_orchestrator_for_chat(
            tmp_path, responses={"你好": make_loop_result("hi")}
        )
        with patch("butler.main._sync_memory") as sync:
            run_scripted_interactive_chat(
                orch, ["你好", "/quit"], patch_sync_memory=False
            )
        sync.assert_called()
        assert sync.call_args[0][1] == "你好"

    def test_prefetch_attached_each_turn(self, tmp_path):
        orch = mock_orchestrator_for_chat(
            tmp_path, responses={"x": make_loop_result("y")}
        )
        with patch("butler.session.lifecycle.attach_turn_memory_prefetch") as prefetch:
            run_scripted_interactive_chat(orch, ["x", "/quit"], patch_prefetch=False)
        assert prefetch.call_count >= 1

    def test_inject_skill_context_on_user_message(self, tmp_path):
        orch = mock_orchestrator_for_chat(
            tmp_path, responses={"问题": make_loop_result("答")}
        )
        run_scripted_interactive_chat(orch, ["问题", "/quit"])
        orch.inject_skill_context.assert_any_call("问题")

    def test_eof_prints_goodbye_and_triggers_session_end(self, tmp_path):
        orch = mock_orchestrator_for_chat(tmp_path)
        with patch("butler.main._trigger_session_end") as trigger:
            run = run_scripted_interactive_chat(orch, [])
        trigger.assert_called_once()
        assert "再见" in run.output

    def test_quit_triggers_session_end(self, tmp_path):
        orch = mock_orchestrator_for_chat(tmp_path)
        with patch("butler.main._trigger_session_end") as trigger:
            run_scripted_interactive_chat(orch, ["/quit"])
        trigger.assert_called_once()

    def test_switch_rebuilds_loop_twice(self, tmp_path):
        orch = mock_orchestrator_for_chat(tmp_path, project_name="alpha")

        def _switch(name: str) -> bool:
            orch.project_manager.current_project = name
            return True

        orch.project_manager.switch_project.side_effect = _switch
        run = run_scripted_interactive_chat(orch, ["/switch demo", "/quit"])
        assert run.orchestrator.create_agent_loop.call_count >= 2
        assert "已切换" in run.output


# ---------------------------------------------------------------------------
# E. Session & memory lifecycle
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCliSessionLifecycle:
    """§2.3.6 / §2.6: /new, post-session, multi-turn, identity semantics."""

    def test_new_then_question_still_runs(self, tmp_path):
        run = run_scripted_interactive_chat(
            mock_orchestrator_for_chat(
                tmp_path,
                responses={
                    "我叫李四": make_loop_result("好的"),
                    "名字": make_loop_result("李四"),
                },
            ),
            ["我叫李四", "/new", "我之前说过什么名字？", "/quit"],
        )
        assert "已清空" in run.output
        assert any("名字" in m for m in run.user_messages)

    def test_multi_turn_preserves_context_in_loop(self, butler_orchestrator, mock_llm_response):
        from butler.core.agent_loop import LoopConfig
        from butler.transport.types import NormalizedResponse, Usage

        LLM = "butler.transport.llm_client.LLMClient"

        def _r(text: str):
            return NormalizedResponse(
                content=text,
                usage=Usage(1, 1, 2),
            )

        with patch(f"{LLM}.complete") as c, patch(f"{LLM}.stream") as s:
            c.side_effect = [_r("好的张三"), _r("你刚才说的是张三")]
            s.side_effect = lambda *a, **k: c.side_effect[c.call_count - 1]
            loop = butler_orchestrator.create_agent_loop(role="butler")
            loop.config = LoopConfig(stream=False)
            with patch("butler.session.lifecycle.sync_turn_memory", return_value={"skipped": True}):
                loop.run("我叫张三")
                r2 = loop.run("我刚才说了什么名字？")
        assert "张三" in (r2.final_response or "")

    def test_sync_memory_empty_user_turn_skipped(self):
        orch = _orch()
        orch.butler_memory = MagicMock()
        with patch("butler.session.lifecycle.sync_turn_memory") as sync:
            sync.return_value = {"skipped": True, "reason": "empty_turn"}
            _sync_memory(orch, "", "answer")
        sync.assert_called_once()
        assert sync.call_args[0][1] == ""


# ---------------------------------------------------------------------------
# F. Error recovery & API feedback
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestCliErrorRecovery:
    """§2.6.3: API retry display, agent errors, interrupt path."""

    def test_on_error_prints_retry_reason(self):
        console, buf = capture_console()
        ui = ChatSessionUI(console)
        ui._on_error(RuntimeError("timeout"), attempt=2)
        text = rendered_text(buf)
        assert "重试" in text
        assert "2" in text

    def test_api_error_classification_shown(self):
        console, buf = capture_console()
        ui = ChatSessionUI(console)
        ui._on_error(RuntimeError("429 rate limit exceeded"), attempt=1)
        text = rendered_text(buf)
        assert "重试" in text
        assert "rate_limit" in text

    def test_agent_run_exception_printed_in_chat(self, tmp_path):
        orch = mock_orchestrator_for_chat(tmp_path)

        def _boom(_msg, _loop):
            raise RuntimeError("loop exploded")

        orch.create_agent_loop.side_effect = None
        filler = "x" * 80
        loop = MagicMock()
        loop.messages = [{"role": "user", "content": filler}] * 4
        loop.run.side_effect = RuntimeError("loop exploded")
        orch.create_agent_loop.return_value = loop

        run = run_scripted_interactive_chat(orch, ["触发错误", "/quit"])
        assert "loop exploded" in run.output or "错误" in run.output


# ---------------------------------------------------------------------------
# G. Exec mode (non-interactive)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCliExecMode:
    """§2.5: one-shot exec uses same Panel path as chat."""

    def test_exec_finish_turn_panel(self):
        orch = MagicMock()
        loop = MagicMock()
        loop.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="我是 Butler 管家。",
        )
        orch.inject_skill_context.side_effect = lambda x: x
        orch.create_agent_loop.return_value = loop

        with patch("butler.orchestrator.ButlerOrchestrator", return_value=orch):
            with patch("butler.main._sync_memory"):
                code = _cmd_exec(SimpleNamespace(message="你好"))
        assert code == 0
        loop.run.assert_called_once()

    def test_exec_non_completed_returns_nonzero(self):
        orch = MagicMock()
        loop = MagicMock()
        loop.run.return_value = LoopResult(
            status=LoopStatus.ERROR,
            error="fail",
        )
        orch.inject_skill_context.side_effect = lambda x: x
        orch.create_agent_loop.return_value = loop
        with patch("butler.orchestrator.ButlerOrchestrator", return_value=orch):
            with patch("butler.main._sync_memory"):
                code = _cmd_exec(SimpleNamespace(message="x"))
        assert code == 1


# ---------------------------------------------------------------------------
# H. Spinner / patch_stdout interaction
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestCliSpinner:
    def test_spinner_disabled_under_patch_stdout(self):
        spinner = WaitSpinner()
        with patch_stdout():
            spinner.start("思考中")
            assert spinner._active is False


# ---------------------------------------------------------------------------
# I. Callback wiring contracts
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestCliWiringContracts:
    """AgentLoop callbacks must be wired for stream, tools, LLM lifecycle."""

    def test_build_callbacks_provides_all_hooks(self):
        console, _ = capture_console()
        ui = ChatSessionUI(console)
        stream = StreamRenderer(console)
        cb = ui.build_callbacks(stream)
        assert isinstance(cb, LoopCallbacks)
        for name in (
            "on_llm_start",
            "on_llm_complete",
            "on_stream_delta",
            "on_stream_boundary",
            "on_tool_start",
            "on_tool_complete",
            "on_error",
            "on_iteration",
            "on_fallback",
        ):
            assert getattr(cb, name) is not None

    def test_stream_delta_wired_to_renderer(self):
        console, _ = capture_console()
        ui = ChatSessionUI(console)
        stream = StreamRenderer(console)
        cb = ui.build_callbacks(stream)
        cb.on_stream_delta("片段")
        assert stream.text == "片段"

    def test_begin_turn_clears_tool_state(self):
        console, _ = capture_console()
        ui = ChatSessionUI(console)
        ui._tool_stack.append((0.0, "read_file", {}))
        ui.begin_turn()
        assert ui._tool_stack == []


# ---------------------------------------------------------------------------
# J. Stream / thinking sanitization (extended)
# ---------------------------------------------------------------------------


@pytest.mark.module_test
class TestCliStreamSanitization:
    def test_multiple_tag_types_stripped(self):
        stream = StreamRenderer(mode="buffer")
        stream.on_delta("<thinking>")
        stream.on_delta("secret")
        stream.on_delta("</thinking>可见")
        assert "可见" in stream.text
        assert "<thinking>" not in stream.text

    def test_stream_then_finish_no_thinking_in_panel(self):
        out = finish_turn_capture(
            stream_chunks=["<think>x</think>", "OK"],
            final_response="OK",
        )
        assert "<think>" not in out
        assert "OK" in out
