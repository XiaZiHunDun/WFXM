"""Tests for remaining P2 improvement items: overview, project todos, pipe, onboarding, workflow resume."""

from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _safe_root(tmp_path, monkeypatch):
    monkeypatch.setenv("BUTLER_TOOL_SAFE_ROOT", str(tmp_path))


class TestProjectOverview:
    """#7 /总览 command."""

    def test_overview_returns_project_list(self, tmp_path, monkeypatch):
        from butler.gateway.message_handler import _build_project_overview

        class FakeProject:
            def __init__(self, name, ptype="software", desc="", workspace=None, pack=""):
                self.name = name
                self.type = ptype
                self.description = desc
                self.workspace = str(workspace or tmp_path / name)
                self.pack = pack

        p1 = FakeProject("ProjectA", desc="描述A", workspace=tmp_path / "pA")
        p2 = FakeProject("ProjectB", desc="描述B", workspace=tmp_path / "pB")

        orch = MagicMock()  # noqa: magicmock-no-spec — p2 remaining features facade (orch)
        orch.project_manager.list_projects.return_value = [p1, p2]
        orch.project_manager.resolve_active_project_name.return_value = "ProjectA"

        result = _build_project_overview(orch, "test:session")
        assert "ProjectA" in result
        assert "ProjectB" in result
        assert "当前" in result
        assert "总览" in result

    def test_overview_empty(self):
        from butler.gateway.message_handler import _build_project_overview

        orch = MagicMock()  # noqa: magicmock-no-spec — p2 remaining features facade (orch)
        orch.project_manager.list_projects.return_value = []
        result = _build_project_overview(orch, "s")
        assert "暂无" in result

    def test_overview_natural_language(self):
        from butler.gateway.message_handler import _normalize_status_request

        assert _normalize_status_request("总览") == "/总览"
        assert _normalize_status_request("所有项目") == "/总览"
        assert _normalize_status_request("列出我Todoist里的所有项目") is None
        assert _normalize_status_request("Todoist今天有哪些待办") is None


class TestProjectTodos:
    """#8 Persistent project-level todos."""

    def test_save_and_load(self, tmp_path):
        from butler.tools.project_todos import _load, _save, _todos_path

        items = [
            {"id": "t1", "content": "写文档", "status": "pending", "priority": "high"},
            {"id": "t2", "content": "跑测试", "status": "in_progress", "priority": "medium"},
        ]
        result = _save(tmp_path, items)
        assert result["ok"] is True
        assert result["count"] == 2

        loaded = _load(tmp_path)
        assert len(loaded) == 2
        assert loaded[0]["priority"] == "high"

    def test_tool_list_no_project(self):
        from butler.tools.project_todos import _tool_project_todos_list

        with patch("butler.tools.project_todos._get_workspace", return_value=None):
            result = json.loads(_tool_project_todos_list())
            assert result["ok"] is False
            assert "NO_ACTIVE_PROJECT" in result["error"]

    def test_tool_write_and_list(self, tmp_path):
        from butler.tools.project_todos import _tool_project_todos_list, _tool_project_todos_write

        with patch("butler.tools.project_todos._get_workspace", return_value=tmp_path):
            write_result = json.loads(_tool_project_todos_write(
                items=[{"content": "任务一"}, {"content": "任务二", "priority": "high"}]
            ))
            assert write_result["ok"] is True
            assert write_result["count"] == 2

            list_result = json.loads(_tool_project_todos_list())
            assert list_result["ok"] is True
            assert list_result["count"] == 2
            assert list_result["open_count"] == 2

    def test_merge_mode(self, tmp_path):
        from butler.tools.project_todos import _tool_project_todos_write

        with patch("butler.tools.project_todos._get_workspace", return_value=tmp_path):
            _tool_project_todos_write(
                items=[{"id": "a", "content": "原始"}, {"id": "b", "content": "另一个"}]
            )
            merge_result = json.loads(_tool_project_todos_write(
                items=[{"id": "a", "status": "completed"}],
                merge=True,
            ))
            assert merge_result["ok"] is True
            assert merge_result["count"] == 2

    def test_format_for_wechat(self, tmp_path):
        from butler.tools.project_todos import _save, format_project_todos_for_wechat

        items = [
            {"id": "1", "content": "写代码", "status": "pending", "priority": "high"},
            {"id": "2", "content": "已完成", "status": "completed", "priority": "low"},
        ]
        _save(tmp_path, items)
        text = format_project_todos_for_wechat(tmp_path)
        assert "写代码" in text
        assert "1 进行中" in text


class TestTerminalPipe:
    """#10 Restricted pipe support."""

    def test_pipe_blocked_by_default(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
        monkeypatch.delenv("BUTLER_TERMINAL_PIPE", raising=False)
        from butler.tools.path_safety import prepare_shell_command

        result = prepare_shell_command("ls | wc -l")
        assert not result.allowed
        assert "metacharacters" in result.error.lower() or "not allowed" in result.error.lower()

    def test_pipe_allowed_with_env(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ENABLE_TERMINAL", "1")
        monkeypatch.setenv("BUTLER_TERMINAL_PIPE", "1")
        from butler.tools.path_safety import prepare_shell_command

        result = prepare_shell_command("ls | wc -l")
        assert result.allowed
        assert result.is_pipe is True
        assert result.argv == ["bash", "-c", "ls | wc -l"]

    def test_pipe_rejects_disallowed_command(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TERMINAL_PIPE", "1")
        from butler.tools.path_safety import prepare_shell_command

        result = prepare_shell_command("ls | rm -rf /")
        assert not result.allowed

    def test_pipe_rejects_other_metacharacters(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TERMINAL_PIPE", "1")
        from butler.tools.path_safety import prepare_shell_command

        result = prepare_shell_command("ls | wc -l; rm -rf /")
        assert not result.allowed

    def test_pipe_max_segments(self, monkeypatch):
        monkeypatch.setenv("BUTLER_TERMINAL_PIPE", "1")
        from butler.tools.path_safety import prepare_shell_command

        result = prepare_shell_command("ls | head | tail | sort | uniq | cut -f1")
        assert not result.allowed
        assert "max 5" in result.error.lower()


class TestOnboardingWelcome:
    """#14 First-time user onboarding."""

    def test_welcome_enabled_by_default(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.message_handler import _WELCOMED_SESSIONS, _maybe_welcome_prefix

        _WELCOMED_SESSIONS.discard("test:user1")
        result = _maybe_welcome_prefix("test:user1")
        assert "Butler" in result
        assert "管家" in result

    def test_no_welcome_when_disabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "0")
        from butler.gateway.message_handler import _WELCOMED_SESSIONS, _maybe_welcome_prefix

        _WELCOMED_SESSIONS.discard("test:disabled_user")
        result = _maybe_welcome_prefix("test:disabled_user")
        assert result == ""

    def test_welcome_with_env(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "1")
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.message_handler import _WELCOMED_SESSIONS, _maybe_welcome_prefix

        _WELCOMED_SESSIONS.discard("test:new_user_test")
        result = _maybe_welcome_prefix("test:new_user_test")
        assert "Butler" in result
        assert "管家" in result

    def test_welcome_only_once(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "1")
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.message_handler import _WELCOMED_SESSIONS, _maybe_welcome_prefix

        _WELCOMED_SESSIONS.discard("test:repeat_user")
        first = _maybe_welcome_prefix("test:repeat_user")
        second = _maybe_welcome_prefix("test:repeat_user")
        assert first != ""
        assert second == ""

    def test_welcome_skipped_when_user_asks_self_intro(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "1")
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.message_handler import _WELCOMED_SESSIONS, _maybe_welcome_prefix

        _WELCOMED_SESSIONS.discard("test:intro_user")
        result = _maybe_welcome_prefix("test:intro_user", "介绍一下你自己")
        assert result == ""
        assert "test:intro_user" in _WELCOMED_SESSIONS
        assert _maybe_welcome_prefix("test:intro_user", "你好") == ""

    def test_welcome_skipped_for_capabilities_question(self, monkeypatch, tmp_path):
        monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "1")
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway.message_handler import _WELCOMED_SESSIONS, _maybe_welcome_prefix

        _WELCOMED_SESSIONS.discard("test:cap_user")
        assert _maybe_welcome_prefix("test:cap_user", "看下你都可以干什么") == ""

    def test_welcome_atomic_under_concurrent_threads(self, monkeypatch, tmp_path):
        """Audit 3.2.1: the in-check + set.add pair is racy. We replace
        _WELCOMED_SESSIONS with a set subclass whose add() sleeps briefly,
        which widens the race window so the bug is reliably observable.
        With the bug: multiple threads see "not in set" and add → multiple
        welcome texts returned. With the lock fix: only one thread passes
        the check-add atomically."""
        import concurrent.futures
        import threading
        import time

        monkeypatch.setenv("BUTLER_ONBOARDING_WELCOME", "1")
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.gateway import handler_helpers
        from butler.gateway.message_handler import _maybe_welcome_prefix

        session = "test:race_user"

        class SlowSet(set):
            def add(self, key):  # type: ignore[override]
                if key == session:
                    time.sleep(0.05)
                return super().add(key)

        handler_helpers._WELCOMED_SESSIONS = SlowSet()

        barrier = threading.Barrier(16)

        def call_welcome():
            barrier.wait()
            return _maybe_welcome_prefix(session)

        with concurrent.futures.ThreadPoolExecutor(max_workers=16) as ex:
            results = list(ex.map(lambda _: call_welcome(), range(16)))

        welcome_count = sum(1 for r in results if r)
        empty_count = sum(1 for r in results if not r)
        assert welcome_count == 1, (
            f"expected exactly 1 welcome text under concurrent threads, got {welcome_count}: "
            f"{[bool(r) for r in results]}"
        )
        assert empty_count == 15


class TestWorkflowAutoResume:
    """#4 Workflow auto-resume after approval."""

    def test_auto_resume_disabled_by_default(self):
        from butler.human_gate import _workflow_auto_resume_enabled

        assert _workflow_auto_resume_enabled() is False

    def test_auto_resume_enabled(self, monkeypatch):
        monkeypatch.setenv("BUTLER_WORKFLOW_AUTO_RESUME", "1")
        from butler.human_gate import _workflow_auto_resume_enabled

        assert _workflow_auto_resume_enabled() is True

    def test_resolve_gate_without_resume(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        from butler.human_gate import (
            _save_pending,
            resolve_human_gate_message,
        )

        from butler.human_gate import PendingGate

        _save_pending("sk1", PendingGate(
            workflow="test-wf", step_id="step1", kind="workflow_step",
        ))
        result = resolve_human_gate_message("sk1", "确认", owner_verified=True)
        assert result is not None
        assert "step1" in result
        assert "/工作流 test-wf" in result

    def test_resolve_gate_with_auto_resume(self, tmp_path, monkeypatch):
        monkeypatch.setenv("BUTLER_HOME", str(tmp_path))
        monkeypatch.setenv("BUTLER_WORKFLOW_AUTO_RESUME", "1")
        from butler.human_gate import (
            PendingGate,
            _save_pending,
            resolve_human_gate_message,
        )

        _save_pending("sk2", PendingGate(
            workflow="test-wf", step_id="step1", kind="workflow_step",
        ))
        with patch(
            "butler.human_gate._auto_resume_workflow",
            return_value="工作流完成 (2/2 步成功)",
        ):
            result = resolve_human_gate_message("sk2", "确认", owner_verified=True)
            assert "自动续跑" in result
            assert "工作流完成" in result
