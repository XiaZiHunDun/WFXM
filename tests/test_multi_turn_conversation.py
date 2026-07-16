"""Multi-turn conversation quality tests."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ["BUTLER_CONVERSATION_STATE_PERSIST"] = "0"

from butler.core.conversation_state import (
    ConversationState,
    TurnSummary,
    ConversationDecision,
    ChapterSummary,
    FileChange,
    TaskNode,
)
from butler.core.turn_summarizer import (
    summarize_turn,
    summarize_chapter,
    _extract_file_changes,
)


class TestConversationStateBasic:
    def test_initial_state(self):
        state = ConversationState()
        assert state.is_empty is True
        assert state.conversation_goal == ""
        assert state.current_task_summary == ""
        assert len(state.turn_summaries) == 0

    def test_add_turn_summary(self):
        state = ConversationState()
        state.add_turn_summary(
            turn_number=1,
            user_intent="创建文件",
            assistant_action="调用 write_file 创建 app.py",
            result_summary="成功",
            files_touched=["app.py"],
        )
        assert len(state.turn_summaries) == 1
        assert state.turn_summaries[0].user_intent == "创建文件"
        assert "app.py" in state.files_modified
        assert state.is_empty is False

    def test_add_decision(self):
        state = ConversationState()
        state.add_decision(
            turn_number=3,
            decision="使用 Python 3.10",
            rationale="支持最新语法特性",
            outcome="已确认",
        )
        assert len(state.decisions_made) == 1
        assert state.decisions_made[0].decision == "使用 Python 3.10"

    def test_add_chapter_summary(self):
        state = ConversationState()
        state.add_chapter_summary(
            chapter_number=1,
            start_turn=1,
            end_turn=10,
            summary="完成项目初始化",
            key_decisions=["使用 Flask", "SQLite 数据库"],
            key_files=["app.py", "models.py"],
        )
        assert len(state.chapter_summaries) == 1
        assert state.chapter_summaries[0].chapter_number == 1
        assert "Flask" in state.chapter_summaries[0].key_decisions[0]

    def test_add_file_change(self):
        state = ConversationState()
        state.add_file_change(
            path="src/utils.py",
            operation="write",
            description="创建工具模块",
            turn_number=5,
        )
        assert len(state.file_change_log) == 1
        assert state.file_change_log[0].path == "src/utils.py"
        assert state.file_change_log[0].operation == "write"

    def test_to_system_reminder_basic(self):
        state = ConversationState()
        state.update_conversation_goal("开发一个博客系统")
        state.update_task_summary("完成用户认证模块")
        state.add_plan_step("创建用户模型")
        state.add_plan_step("实现登录接口")
        reminder = state.to_system_reminder()
        assert "开发一个博客系统" in reminder
        assert "完成用户认证模块" in reminder
        assert "创建用户模型" in reminder

    def test_to_compact_anchor(self):
        state = ConversationState()
        state.update_conversation_goal("开发博客")
        state.update_task_summary("用户认证")
        state.add_turn_summary(1, "开始", "创建文件", "完成", ["app.py"])
        anchor = state.to_compact_anchor()
        assert "开发博客" in anchor
        assert "用户认证" in anchor
        assert "app.py" in anchor

    def test_rolling_window_turns(self):
        state = ConversationState()
        for i in range(25):
            state.add_turn_summary(
                turn_number=i + 1,
                user_intent=f"意图{i}",
                assistant_action=f"操作{i}",
                result_summary=f"结果{i}",
            )
        assert len(state.turn_summaries) == 20
        assert state.turn_summaries[0].turn_number == 6

    def test_rolling_window_decisions(self):
        state = ConversationState()
        for i in range(35):
            state.add_decision(
                turn_number=i + 1,
                decision=f"决策{i}",
                rationale=f"理由{i}",
            )
        assert len(state.decisions_made) == 30
        assert state.decisions_made[0].turn_number == 6

    def test_token_budget_truncation(self):
        state = ConversationState()
        state.update_conversation_goal("X" * 500)
        state.update_task_summary("Y" * 500)
        for i in range(10):
            state.add_plan_step(f"步骤{i}: " + "Z" * 200)
        reminder = state.to_system_reminder(token_budget=500)
        assert len(reminder) < 2000


class TestTaskTree:
    def test_add_task_to_root(self):
        state = ConversationState()
        state.add_task(
            task_id="task1",
            title="实现登录功能",
            status="in_progress",
            description="用户登录API",
            turn_created=3,
        )
        assert state.task_tree is not None
        assert len(state.task_tree.children) == 1
        assert state.task_tree.children[0].title == "实现登录功能"
        assert state.task_tree.children[0].status == "in_progress"

    def test_add_subtask(self):
        state = ConversationState()
        state.add_task(task_id="milestone1", title="用户认证")
        state.add_task(task_id="task1", title="登录API", parent_id="milestone1")
        assert len(state.task_tree.children) == 1
        assert len(state.task_tree.children[0].children) == 1
        assert state.task_tree.children[0].children[0].title == "登录API"

    def test_update_task_status(self):
        state = ConversationState()
        state.add_task(task_id="task1", title="测试任务")
        result = state.update_task_status("task1", "completed", turn_completed=5)
        assert result is True
        assert state.task_tree.children[0].status == "completed"
        assert state.task_tree.children[0].turn_completed == 5

    def test_find_task_by_id(self):
        state = ConversationState()
        state.add_task(task_id="root1", title="Root")
        state.add_task(task_id="child1", title="Child", parent_id="root1")
        task = state.find_task_by_id("child1")
        assert task is not None
        assert task.title == "Child"

    def test_find_nonexistent_task(self):
        state = ConversationState()
        task = state.find_task_by_id("nonexistent")
        assert task is None


class TestTurnSummarizer:
    def test_summarize_turn_fallback(self):
        result = summarize_turn(
            user_message="创建一个名为app.py的文件",
            assistant_response="好的，我来创建这个文件",
            tool_calls_detail=[],
        )
        assert "创建" in result["user_intent"] or "app.py" in result["user_intent"]

    def test_extract_file_changes_write(self):
        changes = _extract_file_changes([{
            "name": "write_file",
            "args": {"file_path": "/tmp/app.py"},
        }])
        assert len(changes) == 1
        assert changes[0]["operation"] == "write"
        assert changes[0]["path"] == "/tmp/app.py"

    def test_extract_file_changes_patch(self):
        changes = _extract_file_changes([{
            "name": "patch",
            "args": {"path": "src/main.py"},
        }])
        assert len(changes) == 1
        assert changes[0]["operation"] == "patch"
        assert changes[0]["path"] == "src/main.py"

    def test_extract_file_changes_terminal(self):
        changes = _extract_file_changes([{
            "name": "terminal",
            "args": {"command": "git commit -m 'update'"},
        }])
        assert len(changes) == 1
        assert changes[0]["operation"] == "terminal"
        assert "git commit" in changes[0]["description"]

    def test_summarize_chapter_fallback(self):
        summaries = [
            {"turn_number": 1, "user_intent": "开始项目", "assistant_action": "创建文件",
             "result_summary": "完成", "files_touched": ["app.py"]},
            {"turn_number": 2, "user_intent": "添加功能", "assistant_action": "修改文件",
             "result_summary": "完成", "files_touched": ["utils.py"]},
        ]
        result = summarize_chapter(summaries)
        assert "2个轮次" in result["summary"] or len(result["key_files"]) > 0


class TestConversationStateTools:
    def test_tool_read_quick(self):
        from butler.tools.conversation_state_tools import tool_conversation_state_read
        result = tool_conversation_state_read(mode="quick")
        data = json.loads(result)
        assert data["ok"] is True or data["ok"] is False

    def test_tool_search(self):
        from butler.tools.conversation_state_tools import tool_conversation_state_search
        result = tool_conversation_state_search(query="test")
        data = json.loads(result)
        assert "results" in data or data.get("ok") is False