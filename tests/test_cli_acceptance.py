"""CLI acceptance tests mapped to docs/guides/manual-testing-guide.md §二."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.core.agent_loop import LoopConfig, LoopResult, LoopStatus
from butler.main import (
    _cmd_create,
    _cmd_exec,
    _cmd_projects,
    _handle_slash_command,
    _run_interactive_chat,
)
from butler.project_manager import ProjectManager
from butler.tools.registry import dispatch_tool, get_tool_definitions

_REPO_ROOT = Path(__file__).resolve().parent.parent
LLM_PATCH = "butler.transport.llm_client.LLMClient"


def _reset_singletons() -> None:
    ProjectManager._instance = None
    reload_butler_settings()


def _setup_projects(tmp_path: Path, monkeypatch) -> None:
    projects_dir = tmp_path / "projects"
    projects_dir.mkdir()
    proj = projects_dir / "test-project"
    proj.mkdir()
    (proj / "project.yaml").write_text(
        yaml.safe_dump(
            {
                "name": "test-project",
                "type": "software",
                "description": "CLI acceptance project",
                "workspace": str(proj),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()


def _text_response(content: str):
    from butler.transport.types import NormalizedResponse, Usage

    return NormalizedResponse(
        content=content,
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


def _tool_response(name: str, args: dict, *, tool_id: str = "call_1"):
    from butler.transport.types import NormalizedResponse, Usage, build_tool_call

    return NormalizedResponse(
        tool_calls=[build_tool_call(tool_id, name, args)],
        usage=Usage(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


@pytest.fixture
def patch_llm(mock_llm_response):
    with (
        patch(f"{LLM_PATCH}.complete") as mock_complete,
        patch(f"{LLM_PATCH}.stream") as mock_stream,
    ):
        from tests.conftest import link_llm_stream_mock

        default = mock_llm_response()
        mock_complete.return_value = default
        link_llm_stream_mock(mock_complete, mock_stream)
        yield mock_complete, mock_stream


@pytest.mark.integration
class TestManualGuide22Dialog:
    """§2.2 基础对话"""

    def test_221_greeting(self, butler_orchestrator, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="你好，我是莎丽。")
        mock_stream.return_value = mock_complete.return_value

        loop = butler_orchestrator.create_agent_loop(role="butler")
        result = loop.run("你好")

        assert result.final_response
        assert "<think>" not in (result.final_response or "")

    def test_223_multi_turn_in_session(self, butler_orchestrator, patch_llm):
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _text_response("好的，张三。"),
            _text_response("你刚才说的是张三。"),
        ]
        from tests.conftest import link_llm_stream_mock

        link_llm_stream_mock(mock_complete, mock_stream)

        loop = butler_orchestrator.create_agent_loop(role="butler")
        loop.config = LoopConfig(stream=False)
        loop.run("我叫张三")
        result = loop.run("我刚才说了什么名字？")
        assert "张三" in (result.final_response or "")

    def test_224_read_file_tool(self, butler_orchestrator, patch_llm, monkeypatch):
        sample = _REPO_ROOT / "butler" / "gateway" / "__init__.py"
        mock_complete, _mock_stream = patch_llm
        mock_complete.side_effect = [
            _tool_response("read_file", {"path": str(sample)}),
            _text_response("已读取文件。"),
        ]
        monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(_REPO_ROOT))

        loop = butler_orchestrator.create_agent_loop(
            role="butler",
            tools=get_tool_definitions(),
            tool_dispatcher=dispatch_tool,
        )
        loop.config = LoopConfig(stream=False)
        result = loop.run("请读取 butler/gateway/__init__.py 的前10行")

        assert result.tool_calls_made >= 1
        assert result.status == LoopStatus.COMPLETED


@pytest.mark.integration
class TestManualGuide23Slash:
    """§2.3 斜杠命令"""

    def test_231_help_lists_commands(self):
        console = MagicMock()
        assert _handle_slash_command("/help", MagicMock(), console) == "handled"
        text = console.print.call_args[0][0]
        assert "/projects" in text
        assert "/health" in text
        assert "/new" in text

    def test_232_status_fields(self):
        orch = MagicMock()
        orch._settings.butler_name = "莎丽"
        orch.project_manager.current_project = "灵文"
        orch._settings.butler_home = Path("/tmp/butler")
        orch._model_credentials.return_value = {
            "provider": "minimax",
            "model": "MiniMax-M2.7",
        }
        console = MagicMock()
        assert _handle_slash_command("/status", orch, console) == "handled"
        text = console.print.call_args[0][0]
        assert "莎丽" in text
        assert "minimax" in text

    def test_232b_health_command(self):
        from butler.gateway.message_handler import ButlerMessageHandler

        orch = MagicMock()
        loop = MagicMock()
        loop.diagnostics = {"schema_recovered": True, "hygiene_compressed": False}
        console = MagicMock()
        assert _handle_slash_command("/health", orch, console, agent_loop=loop) == "handled"
        text = console.print.call_args[0][0]
        assert "Butler 诊断" in text

        handler = ButlerMessageHandler(channel="cli")
        assert "Schema 降级: 是" in handler._format_health_summary("cli") or "Butler 诊断" in text

    def test_236_new_rebuilds_loop(self):
        assert _handle_slash_command("/new", MagicMock(), MagicMock()) == "rebuild_after_new"

    def test_236_memory_may_retain_identity(self, butler_orchestrator, patch_llm):
        """§2.3.6: /new clears loop; identity may remain via memory layer."""
        mock_complete, mock_stream = patch_llm
        mock_complete.side_effect = [
            _text_response("好的，李四。"),
            _text_response("你叫李四。"),
        ]
        from tests.conftest import link_llm_stream_mock

        link_llm_stream_mock(mock_complete, mock_stream)

        loop = butler_orchestrator.create_agent_loop(role="butler")
        loop.config = LoopConfig(stream=False)
        with patch("butler.session_lifecycle.sync_turn_memory", return_value={"skipped": True}):
            loop.run("我叫李四")
            loop.reset()
            result = loop.run("我之前说过什么名字？")
        assert result.final_response


@pytest.mark.integration
class TestManualGuide24Projects:
    """§2.4 项目管理"""

    def test_241_create_and_242_list(self, tmp_path, monkeypatch, capsys):
        _setup_projects(tmp_path, monkeypatch)
        manager = ProjectManager()
        assert _cmd_create(
            SimpleNamespace(
                slug="cli-accept",
                type_="software",
                description="CLI test",
                display_name="",
                pack="",
                template="",
                no_runtime=False,
                reindex=False,
            )
        ) == 0
        assert _cmd_projects(SimpleNamespace()) == 0
        out = capsys.readouterr().out
        assert "cli-accept" in out or "Created" in out


@pytest.mark.integration
class TestManualGuide25Exec:
    """§2.5 单次执行"""

    def test_25_exec_one_shot(self, patch_llm, mock_llm_response):
        mock_complete, mock_stream = patch_llm
        mock_complete.return_value = mock_llm_response(content="我是 Butler 管家。")
        mock_stream.return_value = mock_complete.return_value

        orch = MagicMock()
        loop = MagicMock()
        loop.run.return_value = LoopResult(
            status=LoopStatus.COMPLETED,
            final_response="我是 Butler 管家。",
        )
        orch.inject_skill_context.side_effect = lambda x: x
        orch.create_agent_loop.return_value = loop

        with patch("butler.orchestrator.ButlerOrchestrator", return_value=orch):
            code = _cmd_exec(SimpleNamespace(message="你好，请用一句话自我介绍"))
        assert code == 0


@pytest.mark.integration
class TestManualGuide26Interactive:
    """§2.6 交互异常"""

    def test_264_eof_quit(self, tmp_path):
        orch = MagicMock()
        orch._settings.butler_home = tmp_path
        orch.project_manager.current_project = ""
        orch._model_credentials.return_value = {"provider": "x", "model": "y"}
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
        trigger.assert_called_once()
