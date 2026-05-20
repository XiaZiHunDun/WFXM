"""L3 integration tests for butler.main CLI."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.core.agent_loop import LoopResult, LoopStatus
from butler.main import (
    _build_parser,
    _cmd_create,
    _cmd_exec,
    _cmd_gateway,
    _cmd_projects,
    _handle_slash_command,
    _run_interactive_chat,
    _sync_memory,
    _trigger_session_end,
    main,
)
from butler.project import Project
from butler.project_manager import ProjectManager


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _mock_console():
    console = MagicMock()
    return console


def _mock_orchestrator():
    orch = MagicMock()
    orch.project_manager.list_projects.return_value = []
    orch.project_manager.current_project = ""
    orch.project_manager.switch_project.return_value = False
    orch._settings = MagicMock()
    orch._settings.butler_home = Path("/tmp/butler")
    orch._model_credentials.return_value = {"provider": "minimax", "model": "test"}
    orch.butler_memory = MagicMock()
    orch.butler_memory.experience = MagicMock()
    return orch


@pytest.mark.integration
class TestParser:
    def test_build_parser_parses_subcommands(self):
        p = _build_parser()
        assert p.parse_args(["chat"]).command == "chat"
        assert p.parse_args(["exec", "hello"]).command == "exec"
        assert p.parse_args(["projects"]).command == "projects"
        assert p.parse_args(["create", "myproj"]).command == "create"
        assert p.parse_args(["gateway"]).command == "gateway"

    def test_missing_subcommand_exits(self):
        p = _build_parser()
        with pytest.raises(SystemExit):
            p.parse_args([])


@pytest.mark.integration
class TestSlashCommands:
    def test_help_returns_handled(self):
        console = _mock_console()
        assert _handle_slash_command("/help", _mock_orchestrator(), console) == "handled"
        console.print.assert_called()

    def test_quit_returns_quit(self):
        assert _handle_slash_command("/quit", _mock_orchestrator(), _mock_console()) == "quit"

    def test_status_returns_handled(self):
        assert _handle_slash_command("/status", _mock_orchestrator(), _mock_console()) == "handled"

    def test_projects_returns_handled(self):
        assert _handle_slash_command("/projects", _mock_orchestrator(), _mock_console()) == "handled"

    def test_switch_valid_project_rebuild(self):
        orch = _mock_orchestrator()
        orch.project_manager.switch_project.return_value = True
        orch.project_manager.current_project = "test"
        assert _handle_slash_command("/switch test", orch, _mock_console()) == "rebuild"

    def test_switch_invalid_project_handled(self):
        orch = _mock_orchestrator()
        orch.project_manager.switch_project.return_value = False
        assert _handle_slash_command("/switch missing", orch, _mock_console()) == "handled"

    def test_model_no_args_handled(self):
        assert _handle_slash_command("/model", _mock_orchestrator(), _mock_console()) == "handled"

    def test_model_with_args_rebuild(self):
        orch = _mock_orchestrator()
        assert (
            _handle_slash_command("/model butler minimax/test-model", orch, _mock_console())
            == "rebuild"
        )

    def test_new_returns_rebuild(self):
        assert _handle_slash_command("/new", _mock_orchestrator(), _mock_console()) == "rebuild"

    def test_detail_returns_handled(self):
        with patch("butler.report.get_last_report", return_value=None):
            assert _handle_slash_command("/detail", _mock_orchestrator(), _mock_console()) == "handled"

    def test_unknown_returns_none(self):
        assert _handle_slash_command("/unknown", _mock_orchestrator(), _mock_console()) is None

    def test_health_returns_handled(self):
        orch = _mock_orchestrator()
        loop = MagicMock()
        loop.diagnostics = {"schema_recovered": False}
        console = _mock_console()
        assert _handle_slash_command("/health", orch, console, agent_loop=loop) == "handled"
        console.print.assert_called()


@pytest.mark.integration
class TestSyncMemory:
    def test_valid_messages_calls_experience_add(self):
        orch = _mock_orchestrator()
        _sync_memory(orch, "user question", "assistant answer")
        orch.butler_memory.experience.add.assert_called_once()

    def test_empty_user_msg_skipped(self):
        orch = _mock_orchestrator()
        _sync_memory(orch, "", "answer")
        orch.butler_memory.experience.add.assert_not_called()

    def test_exception_silently_caught(self):
        orch = _mock_orchestrator()
        orch.butler_memory.experience.add.side_effect = RuntimeError("db error")
        _sync_memory(orch, "user", "assistant")


@pytest.mark.integration
class TestCmdExec:
    def test_cmd_exec_runs_and_returns_zero(self):
        orch = MagicMock()
        loop = MagicMock()
        loop.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="exec output",
        )
        orch.inject_skill_context.side_effect = lambda x: x
        orch.create_agent_loop.return_value = loop

        ns = MagicMock(message="run this task")
        with patch("butler.orchestrator.ButlerOrchestrator", return_value=orch):
            code = _cmd_exec(ns)
        assert code == 0
        loop.run.assert_called_once()

    def test_cmd_exec_binds_execution_context(self):
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = MagicMock()
        loop = MagicMock()

        def _run(_message: str) -> LoopResult:
            assert get_current_orchestrator() is orch
            assert get_current_session_key() == "cli"
            return LoopResult(status=LoopStatus.COMPLETED, final_response="exec output")

        loop.run.side_effect = _run
        orch.inject_skill_context.side_effect = lambda x: x
        orch.create_agent_loop.return_value = loop

        ns = MagicMock(message="run this task")
        with patch("butler.orchestrator.ButlerOrchestrator", return_value=orch):
            with patch("butler.session_lifecycle.sync_turn_memory") as sync:
                code = _cmd_exec(ns)
        assert code == 0
        assert sync.call_args.kwargs["session_id"] == "cli"

    def test_sync_memory_uses_current_session_key(self):
        orch = _mock_orchestrator()
        from butler.execution_context import use_execution_context

        with patch("butler.session_lifecycle.sync_turn_memory") as sync:
            with use_execution_context(orch, session_key="cli"):
                _sync_memory(orch, "user", "assistant", status=LoopStatus.COMPLETED)

        assert sync.call_args.kwargs["session_id"] == "cli"

    def test_cmd_exec_exception_returns_one(self):
        orch = MagicMock()
        orch.inject_skill_context.side_effect = lambda x: x
        orch.create_agent_loop.return_value = MagicMock(run=MagicMock(side_effect=RuntimeError("fail")))

        ns = MagicMock(message="fail")
        with patch("butler.orchestrator.ButlerOrchestrator", return_value=orch):
            code = _cmd_exec(ns)
        assert code == 1


@pytest.mark.integration
class TestSessionEnd:
    def test_short_messages_no_processing(self):
        orch = _mock_orchestrator()
        loop = MagicMock(messages=[{"role": "user"}, {"role": "assistant"}])
        with patch("butler.post_session.PostSessionProcessor") as mock_proc:
            _trigger_session_end(orch, loop)
        mock_proc.assert_not_called()

    def test_longer_messages_post_session_called(self):
        orch = _mock_orchestrator()
        loop = MagicMock(
            messages=[
                {"role": "system", "content": "sys"},
                {"role": "user", "content": "1"},
                {"role": "assistant", "content": "2"},
                {"role": "user", "content": "3"},
                {"role": "assistant", "content": "4"},
                {"role": "user", "content": "5"},
            ]
        )
        mock_processor = MagicMock()
        mock_processor.process = MagicMock(return_value={})

        with patch("butler.post_session.PostSessionProcessor", return_value=mock_processor):
            with patch("asyncio.run", return_value={}):
                _trigger_session_end(orch, loop)
        mock_processor.set_llm_call.assert_called_once()


@pytest.mark.integration
class TestMainHelpers:
    def test_stream_renderer_buffers_text(self):
        from butler.cli.stream import StreamRenderer

        console = _mock_console()
        stream = StreamRenderer(console)
        stream.on_delta("hello ")
        stream.on_delta("world")
        assert "hello world" in stream.text

    def test_finish_turn_does_not_duplicate_streamed_reply(self):
        import io

        from butler.cli.session_ui import ChatSessionUI
        from butler.cli.stream import StreamRenderer
        from butler.core.agent_loop import LoopResult, LoopStatus

        console = _mock_console()
        ui = ChatSessionUI(console)
        buf = io.StringIO()
        stream = StreamRenderer(console, output=buf)
        stream.on_delta("你好！我是莎丽。")
        ui.finish_turn(
            LoopResult(
                status=LoopStatus.COMPLETED,
                final_response="你好！我是莎丽。",
                reasoning="internal chain",
            ),
            stream,
        )
        streamed = buf.getvalue()
        assert streamed.count("你好！我是莎丽。") == 1
        bodies = [str(c.args[0]) if c.args else "" for c in console.print.call_args_list]
        joined = "\n".join(bodies)
        assert "你好！我是莎丽。" not in joined
        assert "推理:" not in joined

    def test_main_dispatches_command_and_exits_zero(self):
        with patch("butler.main._cmd_projects", return_value=0) as mock_cmd:
            with pytest.raises(SystemExit) as exc:
                main(["projects"])
        assert exc.value.code == 0
        mock_cmd.assert_called_once()

    def test_main_dispatches_nonzero_exit(self):
        with patch("butler.main._cmd_projects", return_value=7):
            with pytest.raises(SystemExit) as exc:
                main(["projects"])
        assert exc.value.code == 7


@pytest.mark.integration
class TestProjectCommands:
    def test_cmd_projects_no_projects(self):
        manager = MagicMock()
        manager.list_projects.return_value = []
        with patch("butler.project_manager.get_project_manager", return_value=manager):
            assert _cmd_projects(MagicMock()) == 0

    def test_cmd_projects_lists_projects(self):
        project = Project(
            name="demo",
            type="software",
            description="Demo",
            workspace=Path("/tmp/demo"),
        )
        manager = MagicMock()
        manager.list_projects.return_value = [project]
        manager.current_project = "demo"
        with patch("butler.project_manager.get_project_manager", return_value=manager):
            assert _cmd_projects(MagicMock()) == 0

    def test_cmd_create_success(self):
        created = Project(
            name="new-project",
            type="software",
            description="Created",
            workspace=Path("/tmp/new-project"),
        )
        manager = MagicMock()
        manager.create_project.return_value = created
        ns = SimpleNamespace(name="new-project", type_="software", description="Created")
        with patch("butler.project_manager.get_project_manager", return_value=manager):
            assert _cmd_create(ns) == 0
        manager.create_project.assert_called_once_with("new-project", "software", "Created")

    def test_cmd_create_existing_project_returns_one(self):
        manager = MagicMock()
        manager.create_project.return_value = None
        ns = SimpleNamespace(name="exists", type_="software", description="")
        with patch("butler.project_manager.get_project_manager", return_value=manager):
            assert _cmd_create(ns) == 1


@pytest.mark.integration
class TestGatewayCommand:
    def test_cmd_gateway_native_default(self, monkeypatch):
        from butler.main import _cmd_gateway

        ns = MagicMock(platforms="", hermes_remainder=[])
        with patch("butler.gateway.runner.run_gateway_blocking", return_value=0) as run:
            assert _cmd_gateway(ns) == 0
        run.assert_called_once_with(["wechat"])
        assert os.environ["BUTLER_GATEWAY_ACTIVE"] == "1"

    def test_cmd_gateway_hermes_fallback_subprocess(self, monkeypatch):
        from butler.main import _cmd_gateway

        monkeypatch.delenv("HERMES_HOME", raising=False)
        mock_result = MagicMock(returncode=3)
        ns = MagicMock(platforms="wechat", hermes_remainder=["--hermes-fallback", "--debug"])
        with patch("hermes_cli.plugins_cmd._get_enabled_set", return_value=set()) as get_enabled:
            with patch("hermes_cli.plugins_cmd._save_enabled_set") as save_enabled:
                with patch("shutil.which", return_value="/usr/bin/hermes"):
                    with patch("subprocess.run", return_value=mock_result) as run:
                        assert _cmd_gateway(ns) == 3
        get_enabled.assert_called_once()
        save_enabled.assert_called_once_with({"butler", "memory/butler"})
        assert run.call_args.args[0] == [
            "/usr/bin/hermes",
            "gateway",
            "run",
            "--platforms",
            "wechat",
            "--debug",
        ]


@pytest.mark.integration
class TestInteractiveChat:
    def test_interactive_chat_eof_exits_cleanly(self, tmp_path):
        orch = _mock_orchestrator()
        orch._settings.butler_home = tmp_path
        loop = MagicMock(messages=[])
        orch.create_agent_loop.return_value = loop

        class FakeSession:
            def __init__(self, *args, **kwargs):
                pass

            def prompt(self, _prefix):
                raise EOFError

        with patch("prompt_toolkit.PromptSession", FakeSession):
            with patch("butler.main._trigger_session_end") as trigger:
                assert _run_interactive_chat(orch) == 0
        orch.create_agent_loop.assert_called_once()
        trigger.assert_called_once_with(orch, loop)
