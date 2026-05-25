"""L3 integration tests for butler.gateway.message_handler."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from butler.config import reload_butler_settings
from butler.core.agent_loop import LoopResult, LoopStatus
from butler.execution_context import use_execution_context
from butler.gateway.message_handler import (
    ButlerMessageHandler,
    _is_sessionless_command,
    _normalize_detail_request,
    _normalize_status_request,
    _normalize_switch_request,
)
from butler.report import AgentReport, Change, cache_report, clear_report_cache
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

    def test_health_shows_static_memory_layers_without_turn(self, handler):
        text = handler._handle_command("/诊断")
        assert "Butler 诊断" in text
        assert "轮次诊断: 暂无" in text
        assert "记忆分层" in text
        assert "Owner 画像" in text
        assert "--- 有效模型 ---" in text
        assert "gateway(识图)" in text or "gateway(入站媒体)" in text

    def test_health_shows_tool_audit_without_health_snapshot(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        with use_execution_context(handler._orchestrator, session_key="default"):
            dispatch_tool("missing_tool", {})

        text = handler._handle_command("/health")

        assert "Butler 诊断" in text
        assert "会话: default" in text
        assert "轮次诊断: 暂无" in text
        assert "工具调用: 1" in text
        assert "工具失败: 1" in text
        assert "TOOL_NOT_FOUND" in text
        assert "压缩:" not in text

    def test_health_formats_latest_summary(self, handler):
        handler._health_by_session["default"] = {
            "session_key": "default",
            "platform": "test",
            "hygiene_compressed": True,
            "schema_recovered": True,
            "schema_keywords_stripped": 2,
            "skill_context_injected": True,
            "skill_matches": ["python-dev"],
            "memory_context_injected": True,
            "memory_sync": {
                "skipped": False,
                "experience_updates": 1,
                "provider_synced": True,
            },
        }

        text = handler._handle_command("/health")

        assert "Butler 诊断" in text
        assert "会话: default" in text
        assert "压缩: 已压缩" in text
        assert "Schema 降级: 是" in text
        assert "剥离关键字: 2" in text
        assert "Skill: 已注入" in text
        assert "python-dev" in text
        assert "记忆上下文: 已注入" in text
        assert "记忆同步: 已同步" in text

    def test_health_command_uses_current_session_key(self, handler):
        handler._health_by_session["default"] = {"session_key": "default"}
        handler._health_by_session["s1"] = {
            "session_key": "s1",
            "hygiene_compressed": False,
        }

        text = handler.handle_message("/health", session_key="s1")

        assert "会话: s1" in text
        assert "会话: default" not in text

    def test_health_command_does_not_read_other_session_by_arg(self, handler):
        handler._health_by_session["default"] = {"session_key": "default"}
        handler._health_by_session["s1"] = {"session_key": "s1"}

        text = handler._handle_command("/health s1")

        assert "会话: default" in text
        assert "会话: s1" not in text

    def test_health_command_does_not_read_other_session_by_arg_from_gateway(self, handler):
        handler._health_by_session["default"] = {"session_key": "default"}
        handler._health_by_session["s1"] = {"session_key": "s1"}

        text = handler.handle_message("/health s1", session_key="default")

        assert "会话: default" in text
        assert "会话: s1" not in text

    def test_health_redacts_error_details(self, handler):
        handler._health_by_session["default"] = {
            "session_key": "default",
            "error": "provider failed with api_key=secret-token",
            "hygiene_error": "/tmp/private/path failed",
        }

        text = handler._handle_command("/health")

        assert "错误: 有（查看日志）" in text
        assert "压缩错误: 有（查看日志）" in text
        assert "secret-token" not in text
        assert "/tmp/private/path" not in text

    def test_health_includes_tool_audit_summary(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        handler._health_by_session["default"] = {"session_key": "default"}
        with use_execution_context(handler._orchestrator, session_key="default"):
            dispatch_tool("missing_tool", {})

        text = handler._handle_command("/health")

        assert "工具调用: 1" in text
        assert "工具失败: 1" in text
        assert "TOOL_NOT_FOUND" in text

    def test_health_tool_audit_is_session_scoped(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        handler._health_by_session["alice"] = {"session_key": "alice"}
        with use_execution_context(handler._orchestrator, session_key="alice"):
            dispatch_tool("missing_tool", {})
        with use_execution_context(handler._orchestrator, session_key="bob"):
            dispatch_tool("missing_tool", {})
        dispatch_tool("missing_tool", {})

        text = handler._format_health_summary("alice")

        assert "工具调用: 1" in text
        assert "工具失败: 1" in text

    def test_health_tool_audit_filters_session_before_windowing(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        handler._health_by_session["alice"] = {"session_key": "alice"}
        with use_execution_context(handler._orchestrator, session_key="alice"):
            dispatch_tool("missing_tool", {})
        for _ in range(55):
            with use_execution_context(handler._orchestrator, session_key="bob"):
                dispatch_tool("missing_tool", {})

        text = handler._format_health_summary("alice")

        assert "工具调用: 1" in text
        assert "工具失败: 1" in text

    def test_health_tool_audit_uses_session_bucket_not_global_capacity(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        handler._health_by_session["alice"] = {"session_key": "alice"}
        with use_execution_context(handler._orchestrator, session_key="alice"):
            dispatch_tool("missing_tool", {})
        for _ in range(205):
            with use_execution_context(handler._orchestrator, session_key="bob"):
                dispatch_tool("missing_tool", {})

        text = handler._format_health_summary("alice")

        assert "工具调用: 1" in text
        assert "工具失败: 1" in text

    def test_new_clears_current_session_tool_audit(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        handler._health_by_session["alice"] = {"session_key": "alice"}
        with use_execution_context(handler._orchestrator, session_key="alice"):
            dispatch_tool("missing_tool", {})

        handler._handle_command("/new", session_key="alice")
        handler._health_by_session["alice"] = {"session_key": "alice"}
        text = handler._format_health_summary("alice")

        assert "工具调用:" not in text

    def test_model_returns_model_config(self, handler):
        text = handler._handle_command("/model")
        assert "当前有效模型" in text
        assert "butler" in text
        assert "dev_agent" in text

    def test_model_with_args_sets_model(self, handler):
        from butler.tools.registry import dispatch_tool, reset_tool_audit_events

        reset_tool_audit_events()
        handler._health_by_session["default"] = {"stale": True}
        with use_execution_context(handler._orchestrator, session_key="default"):
            dispatch_tool("missing_tool", {})
        text = handler._handle_command("/model butler openai/gpt-4o")
        assert "临时" in text
        assert "openai/gpt-4o" in text
        assert handler.last_health_summary("default") == {}
        handler._health_by_session["default"] = {"session_key": "default"}
        assert "工具调用:" not in handler._format_health_summary("default")

    def test_switch_without_arg_usage_message(self, handler):
        assert handler._handle_command("/switch") == "用法: /switch <项目名称>"

    def test_switch_valid_project_success(self, handler_with_project):
        from butler.session_keys import build_session_key

        sk = build_session_key(platform="test", chat_id="default", project="test-project")
        text = handler_with_project._handle_command("/switch test-project", session_key=sk)
        assert "已切换到项目" in text
        assert "新项目工具" in text or "workspace" in text
        pm = handler_with_project._orchestrator.project_manager
        assert pm.get_project_name_for_chat(platform="test", chat_id="default") == "test-project"

    def test_new_clears_sessions_message(self, handler, mock_loop):
        handler._sessions["default"] = mock_loop
        handler._health_by_session["default"] = {"stale": True}
        with patch(
            "butler.session_lifecycle.trigger_session_end",
            return_value={"memory_updates": 1, "skills_extracted": 0},
        ):
            text = handler._handle_command("/new")
        assert text.startswith("已清空本轮对话上下文。")
        assert "已提炼" in text
        assert handler._sessions == {}
        assert handler.last_health_summary("default") == {}

    def test_new_only_clears_current_session(self, handler):
        loop_a = MagicMock(messages=[{"role": "user"}] * 6)
        loop_b = MagicMock(messages=[{"role": "user"}] * 6)
        handler._sessions["a"] = loop_a
        handler._sessions["b"] = loop_b
        handler._session_registry.touch("a")
        handler._session_registry.touch("b")
        handler._health_by_session["a"] = {"stale": "a"}
        handler._health_by_session["b"] = {"keep": "b"}

        with patch(
            "butler.session_lifecycle.trigger_session_end",
            return_value={"skipped": True, "reason": "short_history"},
        ) as finalize:
            text = handler.handle_message("/new", session_key="a")

        assert text.startswith("已清空本轮对话上下文。")
        finalize.assert_called_once_with(
            handler._orchestrator, loop_a, session_id="a", reason="clear"
        )
        assert "a" not in handler._sessions
        assert handler._sessions["b"] is loop_b
        assert handler.last_health_summary("a") == {}
        assert handler.last_health_summary("b") == {"keep": "b"}

    def test_detail_no_report(self, handler):
        with patch("butler.report.get_last_report", return_value=None):
            text = handler._handle_command("/detail")
        assert "暂无" in text

    def test_normalize_detail_request_aliases(self):
        assert _normalize_detail_request("详细") == "/详细"
        assert _normalize_detail_request("detail") == "/详细"
        assert _normalize_detail_request("详细 变更") == "/详细 变更"
        assert _normalize_detail_request("/详细 变更") == "/详细 变更"
        assert _normalize_detail_request("/详细 决策") == "/详细 决策"
        assert _normalize_detail_request("/detail changes") == "/detail changes"
        assert _normalize_detail_request("刚才删的文件，/详细") == "/详细"
        assert _normalize_detail_request("详细信息") == "/详细"
        assert _normalize_detail_request("我要看一下详细信息") == "/详细"
        assert _normalize_detail_request("看一下详细") == "/详细"
        assert _normalize_detail_request("你好") is None

    def test_normalize_switch_request_aliases(self):
        assert _normalize_switch_request("切换到演示试点") == "/切换 演示试点"
        assert _normalize_switch_request("切换至灵文1号") == "/切换 灵文1号"
        assert _normalize_switch_request("你好") is None

    def test_normalize_status_request_aliases(self):
        assert _normalize_status_request("当前在哪个项目？") == "/状态"
        assert _normalize_status_request("当前是什么项目") == "/状态"
        assert _normalize_status_request("当前是什么项目？灵文项目是做什么的？") is None
        assert _normalize_status_request("你好") is None

    def test_detail_plain_text_skips_llm(self, handler):
        clear_report_cache()
        cache_report(
            AgentReport(
                headline="内容代理已完成任务",
                summary="已写入 docs/wechat-smoke.md",
                changes=[
                    Change(file="docs/wechat-smoke.md", action="created", description=""),
                ],
            ),
            session_key="wechat:s1:_",
        )
        with patch.object(handler, "_get_or_create_loop") as mock_get:
            text = handler.handle_message("详细", session_key="wechat:s1:_", platform="wechat")
        mock_get.assert_not_called()
        assert "wechat-smoke.md" in text

    def test_detail_report_scoped_to_session(self, handler):
        clear_report_cache()
        cache_report(AgentReport(headline="report-for-u1"), session_key="wechat:u1:_")
        cache_report(AgentReport(headline="report-for-u2"), session_key="wechat:u2:_")
        text = handler.handle_message("/详细", session_key="wechat:u1:_", platform="wechat")
        assert "report-for-u1" in text
        assert "report-for-u2" not in text

    def test_chinese_alias_status(self, handler):
        assert handler._handle_command("/状态") is not None

    def test_chinese_alias_projects(self, handler):
        assert handler._handle_command("/项目") == "暂无项目。"

    def test_chinese_alias_new(self, handler):
        with patch(
            "butler.session_lifecycle.trigger_session_end",
            return_value={"skipped": True, "reason": "short_history"},
        ):
            text = handler._handle_command("/新对话")
        assert text.startswith("已清空本轮对话上下文。")

    def test_plan_mode_slash_commands(self, handler):
        from butler.plan_mode import clear_plan_mode, is_plan_mode

        clear_plan_mode("wechat:plan:_")
        on = handler._handle_command("/计划", session_key="wechat:plan:_")
        assert on and "规划模式" in on
        assert is_plan_mode("wechat:plan:_")
        off = handler._handle_command("/执行", session_key="wechat:plan:_")
        assert off and "退出" in off
        assert not is_plan_mode("wechat:plan:_")

    def test_non_command_returns_none(self, handler):
        assert handler._handle_command("/unknowncmd") is None

    def test_sessionless_commands_are_detected(self):
        assert _is_sessionless_command("/switch test-project") is True
        assert _is_sessionless_command("/模型 butler minimax/test") is True
        assert _is_sessionless_command("/批准") is True
        assert _is_sessionless_command("/开发状态") is True
        assert _is_sessionless_command("/new") is True
        assert _is_sessionless_command("/计划") is True
        assert _is_sessionless_command("/任务") is True
        assert _is_sessionless_command("hello") is False
        assert _is_sessionless_command("/unknowncmd") is False

    def test_hook_rewrite_to_global_command_bypasses_session_lock(self, handler):
        with patch(
            "butler.gateway.hooks.apply_pre_gateway_dispatch",
            return_value="/model",
        ):
            with patch.object(
                handler._session_registry,
                "enter_session",
                side_effect=AssertionError("session lock should not be acquired"),
            ):
                text = handler.handle_message("hello", session_key="s1")

        assert "当前有效模型" in text

    def test_slash_command_bypasses_session_entry(self, handler):
        with patch.object(
            handler._session_registry,
            "enter_session",
            side_effect=AssertionError("slash commands should not enter a session turn"),
        ):
            text = handler.handle_message("/status", session_key="s1")

        assert "Butler 状态" in text

    def test_unknown_slash_command_enters_session_turn(self, handler, mock_loop):
        with patch.object(handler, "_get_or_create_loop", return_value=mock_loop):
            with patch("butler.gateway.message_handler.sync_turn_memory", return_value={"skipped": True}):
                text = handler.handle_message("/unknowncmd", session_key="s1")

        assert text == "assistant reply"
        assert mock_loop.run.call_args.args[0] == "/unknowncmd"


@pytest.mark.integration
class TestHandleMessage:
    def test_normal_message_returns_response(self, handler, mock_loop):
        mock_loop.hygiene_compress_if_needed.return_value = True
        mock_loop.run.return_value.diagnostics = {"schema_recovered": True}
        with patch.object(handler, "_get_or_create_loop", return_value=mock_loop):
            with patch("butler.gateway.message_handler.attach_turn_memory_prefetch") as prefetch:
                with patch(
                    "butler.gateway.message_handler.sync_turn_memory",
                    return_value={"skipped": False, "provider_synced": True},
                ) as sync:
                    text = handler.handle_message("hello", session_key="s1")
        assert text == "assistant reply"
        prefetch.assert_called_once()
        mock_loop.run.assert_called_once()
        assert mock_loop.run.call_args.args[0] == "hello"
        mock_loop.hygiene_compress_if_needed.assert_called_once()
        sync.assert_called_once()
        health = handler.last_health_summary("s1")
        assert health["hygiene_compressed"] is True
        assert health["loop"]["schema_recovered"] is True
        assert health["memory_sync"]["provider_synced"] is True

    def test_normal_message_binds_execution_context(self, handler, mock_loop):
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        def _run(_message: str) -> LoopResult:
            assert get_current_orchestrator() is handler._orchestrator
            assert get_current_session_key() == "s1"
            return LoopResult(status=LoopStatus.COMPLETED, final_response="assistant reply")

        mock_loop.run.side_effect = _run
        with patch.object(handler, "_get_or_create_loop", return_value=mock_loop):
            with patch("butler.gateway.message_handler.sync_turn_memory", return_value={"skipped": True}):
                assert handler.handle_message("hello", session_key="s1") == "assistant reply"

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
        assert "boom" not in text


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

    def test_new_keeps_other_sessions(self, handler, mock_loop):
        from butler.session_keys import build_session_key

        sk_default = build_session_key(platform="unknown", chat_id="default", project="")
        other_loop = MagicMock()
        handler._sessions[sk_default] = mock_loop
        handler._sessions["other"] = other_loop
        handler._session_registry.touch(sk_default)
        handler._session_registry.touch("other")

        handler.handle_message("/new", session_key=sk_default)

        assert sk_default not in handler._sessions
        assert handler._sessions["other"] is other_loop

    def test_switch_clears_all_project_sessions_for_chat(self, handler_with_project, mock_loop):
        from butler.session_keys import build_session_key

        sk_other = build_session_key(platform="test", chat_id="default", project="other-proj")
        handler_with_project._sessions[sk_other] = mock_loop
        handler_with_project._session_registry.touch(sk_other)
        handler_with_project.handle_message("/switch test-project", platform="test", external_id="default")
        assert sk_other not in handler_with_project._sessions

    def test_get_or_create_loop_evicts_idle_sessions(self, handler):
        now = {"value": 0.0}
        handler._session_registry.idle_ttl_seconds = 10
        handler._session_registry._now = lambda: now["value"]
        old_loop = MagicMock(messages=[{"role": "user"}] * 6)
        new_loop = MagicMock()
        handler._sessions["old"] = old_loop
        handler._session_registry.touch("old")
        now["value"] = 20.0

        with patch.object(handler._orchestrator, "create_agent_loop", return_value=new_loop):
            with patch("butler.session_lifecycle.trigger_session_end", return_value={}) as finalize:
                loop = handler._get_or_create_loop("new")

        assert loop is new_loop
        assert "old" not in handler._sessions
        assert "new" in handler._sessions
        finalize.assert_called_once_with(
            handler._orchestrator, old_loop, reason="finalize"
        )

    def test_get_or_create_loop_enforces_lru_limit(self, handler):
        now = {"value": 0.0}
        handler._session_registry.max_sessions = 2
        handler._session_registry._now = lambda: now["value"]
        loops = [MagicMock(name=f"loop-{i}") for i in range(3)]

        with patch.object(handler._orchestrator, "create_agent_loop", side_effect=loops):
            for key in ("a", "b", "c"):
                now["value"] += 1.0
                handler._get_or_create_loop(key)

        assert set(handler._sessions) == {"b", "c"}
