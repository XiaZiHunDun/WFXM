"""L0 Fast Unit Tests — ~50 tests covering core ConversationState functionality.

These tests run in < 1 second and validate basic data structure operations,
boundary conditions, and invariants. Run on every commit.
"""

import pytest

from butler.core.conversation_state import (
    ConversationState,
    TurnSummary,
    ConversationDecision,
    ChapterSummary,
    FileChange,
    TaskNode,
    build_conversation_reminder,
)


@pytest.mark.l0
class TestConversationStateBasic:
    def test_initial_state_empty(self, empty_conversation_state: ConversationState):
        assert empty_conversation_state.is_empty is True
        assert empty_conversation_state.conversation_goal == ""
        assert empty_conversation_state.current_task_summary == ""
        assert empty_conversation_state.turn_summaries == []
        assert empty_conversation_state.decisions_made == []
        assert empty_conversation_state.files_modified == []
        assert empty_conversation_state.current_plan_steps == []
        assert empty_conversation_state.open_questions == []
        assert empty_conversation_state.chapter_summaries == []
        assert empty_conversation_state.file_change_log == []
        assert empty_conversation_state.task_tree is None

    def test_add_single_turn_summary(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(1, "创建文件", "调用write_file", "成功", ["app.py"])
        assert len(state.turn_summaries) == 1
        assert state.turn_summaries[0].turn_number == 1
        assert state.turn_summaries[0].user_intent == "创建文件"
        assert state.turn_summaries[0].assistant_action == "调用write_file"
        assert state.turn_summaries[0].result_summary == "成功"
        assert state.turn_summaries[0].files_touched == ["app.py"]
        assert "app.py" in state.files_modified
        assert state.is_empty is False

    def test_add_single_decision(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_decision(3, "使用Python 3.10", "支持最新语法", "已确认")
        assert len(state.decisions_made) == 1
        assert state.decisions_made[0].turn_number == 3
        assert state.decisions_made[0].decision == "使用Python 3.10"
        assert state.decisions_made[0].rationale == "支持最新语法"
        assert state.decisions_made[0].outcome == "已确认"

    def test_add_single_chapter_summary(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_chapter_summary(1, 1, 10, "完成项目初始化", ["Flask框架"], ["app.py"])
        assert len(state.chapter_summaries) == 1
        assert state.chapter_summaries[0].chapter_number == 1
        assert state.chapter_summaries[0].start_turn == 1
        assert state.chapter_summaries[0].end_turn == 10
        assert state.chapter_summaries[0].summary == "完成项目初始化"
        assert state.chapter_summaries[0].key_decisions == ["Flask框架"]
        assert state.chapter_summaries[0].key_files == ["app.py"]

    def test_add_single_file_change(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_file_change("src/utils.py", "write", "创建工具模块", 5)
        assert len(state.file_change_log) == 1
        assert state.file_change_log[0].path == "src/utils.py"
        assert state.file_change_log[0].operation == "write"
        assert state.file_change_log[0].description == "创建工具模块"
        assert state.file_change_log[0].turn_number == 5

    def test_update_conversation_goal(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.update_conversation_goal("开发博客系统")
        assert state.conversation_goal == "开发博客系统"

    def test_update_task_summary(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.update_task_summary("完成用户认证")
        assert state.current_task_summary == "完成用户认证"

    def test_add_and_remove_plan_step(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_plan_step("创建模型")
        state.add_plan_step("实现API")
        assert len(state.current_plan_steps) == 2
        assert "创建模型" in state.current_plan_steps
        state.remove_plan_step("创建模型")
        assert len(state.current_plan_steps) == 1
        assert "创建模型" not in state.current_plan_steps

    def test_add_and_resolve_open_question(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_open_question("使用MySQL还是PostgreSQL?")
        state.add_open_question("使用REST还是GraphQL?")
        assert len(state.open_questions) == 2
        assert "使用MySQL还是PostgreSQL?" in state.open_questions
        state.resolve_open_question("使用MySQL还是PostgreSQL?")
        assert len(state.open_questions) == 1
        assert "使用MySQL还是PostgreSQL?" not in state.open_questions

    def test_add_and_remove_pending_todo(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_pending_todo("修复bug")
        state.add_pending_todo("编写测试")
        assert len(state.pending_todos) == 2
        assert "修复bug" in state.pending_todos
        state.remove_pending_todo("修复bug")
        assert len(state.pending_todos) == 1
        assert "修复bug" not in state.pending_todos


@pytest.mark.l0
class TestRollingWindows:
    def test_turn_summaries_rolling_window_exact_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(20):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", f"结果{i}")
        assert len(state.turn_summaries) == 20
        assert state.turn_summaries[0].turn_number == 1

    def test_turn_summaries_rolling_window_over_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(30):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", f"结果{i}")
        assert len(state.turn_summaries) == 20
        assert state.turn_summaries[0].turn_number == 11

    def test_decisions_rolling_window_exact_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(30):
            state.add_decision(i + 1, f"决策{i}", f"理由{i}")
        assert len(state.decisions_made) == 30
        assert state.decisions_made[0].turn_number == 1

    def test_decisions_rolling_window_over_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(40):
            state.add_decision(i + 1, f"决策{i}", f"理由{i}")
        assert len(state.decisions_made) == 30
        assert state.decisions_made[0].turn_number == 11

    def test_chapters_rolling_window_exact_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(10):
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
        assert len(state.chapter_summaries) == 10
        assert state.chapter_summaries[0].chapter_number == 1

    def test_chapters_rolling_window_over_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(15):
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
        assert len(state.chapter_summaries) == 10
        assert state.chapter_summaries[0].chapter_number == 6

    def test_file_changes_rolling_window_exact_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(50):
            state.add_file_change(f"file{i}.py", "write", f"描述{i}", i + 1)
        assert len(state.file_change_log) == 50
        assert state.file_change_log[0].path == "file0.py"

    def test_file_changes_rolling_window_over_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(60):
            state.add_file_change(f"file{i}.py", "write", f"描述{i}", i + 1)
        assert len(state.file_change_log) == 50
        assert state.file_change_log[0].path == "file10.py"

    def test_open_questions_rolling_window_over_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(20):
            state.add_open_question(f"问题{i}")
        assert len(state.open_questions) == 15
        assert "问题0" not in state.open_questions
        assert "问题19" in state.open_questions

    def test_plan_steps_rolling_window_over_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(25):
            state.add_plan_step(f"步骤{i}")
        assert len(state.current_plan_steps) == 20
        assert "步骤0" not in state.current_plan_steps
        assert "步骤24" in state.current_plan_steps


@pytest.mark.l0
class TestFieldTruncation:
    def test_turn_summary_fields_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_text = "X" * 600
        state.add_turn_summary(1, long_text, long_text, long_text)
        assert len(state.turn_summaries[0].user_intent) == 500
        assert len(state.turn_summaries[0].assistant_action) == 500
        assert len(state.turn_summaries[0].result_summary) == 500

    def test_decision_fields_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_text = "X" * 600
        state.add_decision(1, long_text, long_text, long_text)
        assert len(state.decisions_made[0].decision) == 300
        assert len(state.decisions_made[0].rationale) == 500
        assert len(state.decisions_made[0].outcome) == 300

    def test_chapter_summary_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_summary = "X" * 1500
        long_decisions = ["X" * 400] * 10
        long_files = ["X" * 300] * 15
        state.add_chapter_summary(1, 1, 10, long_summary, long_decisions, long_files)
        assert len(state.chapter_summaries[0].summary) == 1000
        assert len(state.chapter_summaries[0].key_decisions) == 5
        assert len(state.chapter_summaries[0].key_files) == 10

    def test_file_change_fields_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_op = "X" * 30
        long_desc = "X" * 300
        state.add_file_change("path.py", long_op, long_desc, 1)
        assert len(state.file_change_log[0].operation) == 20
        assert len(state.file_change_log[0].description) == 200

    def test_conversation_goal_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_goal = "X" * 600
        state.update_conversation_goal(long_goal)
        assert len(state.conversation_goal) == 500

    def test_task_summary_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_summary = "X" * 1200
        state.update_task_summary(long_summary)
        assert len(state.current_task_summary) == 1000

    def test_plan_step_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_step = "X" * 300
        state.add_plan_step(long_step)
        assert len(state.current_plan_steps[0]) == 200

    def test_open_question_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_question = "X" * 300
        state.add_open_question(long_question)
        assert len(state.open_questions[0]) == 200

    def test_pending_todo_truncation(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_todo = "X" * 400
        state.add_pending_todo(long_todo)
        assert len(state.pending_todos[0]) == 300


@pytest.mark.l0
class TestTaskTree:
    def test_add_task_to_empty_tree(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_task("task1", "实现登录", "in_progress", "用户登录API", turn_created=1)
        assert state.task_tree is not None
        assert state.task_tree.id == "root"
        assert state.task_tree.title == "Project"
        assert len(state.task_tree.children) == 1
        assert state.task_tree.children[0].id == "task1"
        assert state.task_tree.children[0].title == "实现登录"
        assert state.task_tree.children[0].status == "in_progress"

    def test_add_nested_subtask(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_task("milestone1", "用户认证")
        state.add_task("task1", "登录API", parent_id="milestone1")
        state.add_task("subtask1", "密码加密", parent_id="task1")
        assert len(state.task_tree.children) == 1
        assert len(state.task_tree.children[0].children) == 1
        assert len(state.task_tree.children[0].children[0].children) == 1
        assert state.task_tree.children[0].children[0].children[0].title == "密码加密"

    def test_update_task_status(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_task("task1", "测试任务")
        result = state.update_task_status("task1", "completed", 5)
        assert result is True
        assert state.task_tree.children[0].status == "completed"
        assert state.task_tree.children[0].turn_completed == 5

    def test_update_nonexistent_task_status(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        result = state.update_task_status("nonexistent", "completed")
        assert result is False

    def test_find_task_by_id(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_task("root1", "根任务")
        state.add_task("child1", "子任务", parent_id="root1")
        state.add_task("grandchild1", "孙任务", parent_id="child1")
        found = state.find_task_by_id("grandchild1")
        assert found is not None
        assert found.title == "孙任务"

    def test_find_nonexistent_task(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        found = state.find_task_by_id("nonexistent")
        assert found is None

    def test_task_node_to_dict(self):
        node = TaskNode("id1", "标题", "completed", "描述", "parent1", [], 1, 5)
        data = node.to_dict()
        assert data["id"] == "id1"
        assert data["title"] == "标题"
        assert data["status"] == "completed"
        assert data["description"] == "描述"
        assert data["parent_id"] == "parent1"
        assert data["turn_created"] == 1
        assert data["turn_completed"] == 5
        assert data["children"] == []

    def test_task_node_from_dict(self):
        data = {
            "id": "id1",
            "title": "标题",
            "status": "in_progress",
            "description": "描述",
            "parent_id": "parent1",
            "turn_created": 1,
            "turn_completed": 0,
            "children": [{"id": "child1", "title": "子任务"}],
        }
        node = TaskNode.from_dict(data)
        assert node.id == "id1"
        assert node.title == "标题"
        assert node.status == "in_progress"
        assert len(node.children) == 1
        assert node.children[0].id == "child1"


@pytest.mark.l0
class TestReset:
    def test_reset_empty_state(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.reset()
        assert state.is_empty is True

    def test_reset_populated_state(self, populated_conversation_state: ConversationState):
        state = populated_conversation_state
        assert state.is_empty is False
        state.reset()
        assert state.is_empty is True
        assert state.conversation_goal == ""
        assert state.current_task_summary == ""
        assert state.task_tree is None


@pytest.mark.l0
class TestSystemReminder:
    def test_empty_state_reminder(self, empty_conversation_state: ConversationState):
        reminder = empty_conversation_state.to_system_reminder()
        assert reminder == ""

    def test_basic_reminder_content(self, populated_conversation_state: ConversationState):
        state = populated_conversation_state
        reminder = state.to_system_reminder()
        assert "开发一个电商平台" in reminder
        assert "完成用户认证模块" in reminder
        assert "创建用户模型" in reminder

    def test_reminder_token_budget_respected(self, full_conversation_state: ConversationState):
        state = full_conversation_state
        reminder = state.to_system_reminder(token_budget=500)
        assert len(reminder) < 2000

    def test_reminder_priority_order(self, populated_conversation_state: ConversationState):
        state = populated_conversation_state
        reminder = state.to_system_reminder()
        goal_pos = reminder.find("对话目标")
        task_pos = reminder.find("当前任务")
        plan_pos = reminder.find("执行计划")
        assert goal_pos < task_pos < plan_pos


@pytest.mark.l0
class TestCompactAnchor:
    def test_empty_state_anchor(self, empty_conversation_state: ConversationState):
        anchor = empty_conversation_state.to_compact_anchor()
        assert anchor == ""

    def test_basic_anchor_content(self, populated_conversation_state: ConversationState):
        state = populated_conversation_state
        anchor = state.to_compact_anchor()
        assert "开发一个电商平台" in anchor
        assert "完成用户认证模块" in anchor

    def test_anchor_truncation(self, full_conversation_state: ConversationState):
        state = full_conversation_state
        anchor = state.to_compact_anchor()
        assert len(anchor) < 1000


@pytest.mark.l0
class TestBuildConversationReminder:
    def test_empty_state_build_reminder(self, empty_conversation_state: ConversationState):
        reminder = build_conversation_reminder(empty_conversation_state)
        assert reminder == ""

    def test_populated_state_build_reminder(self, populated_conversation_state: ConversationState):
        reminder = build_conversation_reminder(populated_conversation_state)
        assert "<conversation-state>" in reminder
        assert "</conversation-state>" in reminder
        assert "开发一个电商平台" in reminder
