"""L3 integration tests for butler.gateway.message_handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.core.agent_loop import LoopResult, LoopStatus
from butler.gateway.message_handler import ButlerMessageHandler
from butler.project_manager import ProjectManager
from butler.report import AgentReport, cache_report


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
                "description": "Gateway test project",
                "workspace": str(proj),
            },
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(projects_dir))
    _reset_singletons()


@pytest.fixture
def handler(tmp_path, monkeypatch, tmp_butler_home):
    empty_projects = tmp_path / "empty-projects"
    empty_projects.mkdir()
    monkeypatch.setenv("BUTLER_PROJECTS_DIR", str(empty_projects))
    _reset_singletons()
    return ButlerMessageHandler(channel="test")


@pytest.fixture
def handler_with_project(tmp_path, monkeypatch, tmp_butler_home):
    _setup_projects(tmp_path, monkeypatch)
    h = ButlerMessageHandler(channel="test")
    h._orchestrator.project_manager.switch_project("test-project")
    return h


@pytest.fixture
def mock_loop():
    loop = MagicMock()
    loop.run.return_value = LoopResult(
        status=LoopStatus.COMPLETED,
        final_response="assistant reply",
    )
    return loop


@pytest.mark.integration
class TestSlashCommands:
    def test_projects_empty_returns_no_projects_message(self, handler):
        assert handler._handle_command("/projects") == "暂无项目。"

    def test_projects_lists_projects(self, handler_with_project):
        text = handler_with_project._handle_command("/projects")
        assert "test-project" in text

    def test_status_returns_status_string(self, handler):
        text = handler._handle_command("/status")
        assert text is not None
        assert "Butler" in text
        assert "当前项目" in text

    def test_model_returns_model_config(self, handler):
        text = handler._handle_command("/model")
        assert "butler" in text
        assert "dev_agent" in text

    def test_model_with_args_sets_model(self, handler):
        text = handler._handle_command("/model butler openai/gpt-4o")
        assert "已设置" in text
        assert "openai/gpt-4o" in text

    def test_switch_without_arg_usage_message(self, handler):
        assert handler._handle_command("/switch") == "用法: /switch <项目名称>"

    def test_switch_valid_project_success(self, handler_with_project):
        text = handler_with_project._handle_command("/switch test-project")
        assert "已切换到项目" in text

    def test_new_clears_sessions_message(self, handler, mock_loop):
        handler._sessions["default"] = mock_loop
        assert handler._handle_command("/new") == "已清空对话历史。"
        assert handler._sessions == {}

    def test_detail_no_report(self, handler):
        with patch("butler.report.get_last_report", return_value=None):
            text = handler._handle_command("/detail")
        assert "暂无" in text

    def test_chinese_alias_status(self, handler):
        assert handler._handle_command("/状态") is not None

    def test_chinese_alias_projects(self, handler):
        assert handler._handle_command("/项目") == "暂无项目。"

    def test_chinese_alias_new(self, handler):
        assert handler._handle_command("/新对话") == "已清空对话历史。"

    def test_non_command_returns_none(self, handler):
        assert handler._handle_command("/unknowncmd") is None


@pytest.mark.integration
class TestHandleMessage:
    def test_normal_message_returns_response(self, handler, mock_loop):
        with patch.object(handler, "_get_or_create_loop", return_value=mock_loop):
            text = handler.handle_message("hello", session_key="s1")
        assert text == "assistant reply"
        mock_loop.run.assert_called_once()

    def test_empty_message_returns_empty(self, handler):
        assert handler.handle_message("") == ""
        assert handler.handle_message("   ") == ""

    def test_slash_command_direct_response_no_agent_loop(self, handler, mock_loop):
        handler._sessions["default"] = mock_loop
        text = handler.handle_message("/status")
        assert "Butler" in text
        mock_loop.run.assert_not_called()

    def test_exception_in_loop_returns_error_message(self, handler, mock_loop):
        mock_loop.run.side_effect = RuntimeError("boom")
        with patch.object(handler, "_get_or_create_loop", return_value=mock_loop):
            text = handler.handle_message("fail me", session_key="err")
        assert "处理失败" in text
        assert "boom" in text


@pytest.mark.integration
class TestFormatResponse:
    def test_wechat_truncates_to_2000_chars(self, handler):
        long_text = "x" * 3000
        result = LoopResult(status=LoopStatus.COMPLETED, final_response=long_text)
        out = handler._format_response(result, platform="wechat")
        assert len(out) <= 2000

    def test_empty_final_response_placeholder(self, handler):
        result = LoopResult(status=LoopStatus.COMPLETED, final_response=None)
        assert handler._format_response(result, "cli") == "（执行完成，无文字输出）"

    def test_default_platform_full_text(self, handler):
        result = LoopResult(status=LoopStatus.COMPLETED, final_response="full body")
        assert handler._format_response(result, "cli") == "full body"


@pytest.mark.integration
class TestSessionManagement:
    def test_different_session_keys_different_loops(self, handler):
        loop_a = MagicMock()
        loop_b = MagicMock()
        calls = {"n": 0}

        def _factory(key: str):
            calls["n"] += 1
            return loop_a if key == "a" else loop_b

        with patch.object(handler._orchestrator, "create_agent_loop", side_effect=lambda **_: loop_a):
            with patch.object(handler, "_get_or_create_loop", side_effect=_factory):
                handler._sessions.clear()
                handler._sessions["a"] = loop_a
                handler._sessions["b"] = loop_b
                assert handler._get_or_create_loop("a") is loop_a
                assert handler._get_or_create_loop("b") is loop_b
                assert handler._get_or_create_loop("a") is not handler._get_or_create_loop("b")

    def test_new_clears_all_sessions(self, handler, mock_loop):
        handler._sessions = {"a": mock_loop, "b": mock_loop}
        handler.handle_message("/new")
        assert handler._sessions == {}

    def test_switch_clears_all_sessions(self, handler_with_project, mock_loop):
        handler_with_project._sessions = {"default": mock_loop}
        handler_with_project.handle_message("/switch test-project")
        assert handler_with_project._sessions == {}
