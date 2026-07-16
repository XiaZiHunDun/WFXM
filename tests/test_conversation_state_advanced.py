"""Advanced conversation state tests — including real LLM multi-turn validation."""

import json
import os
import pytest
from unittest.mock import MagicMock, patch

os.environ["BUTLER_CONVERSATION_STATE_PERSIST"] = "0"

from butler.core.conversation_state import (
    ConversationState,
    TaskNode,
)
from butler.core.turn_summarizer import (
    summarize_chapter,
    _extract_file_changes,
)


class TestChapterSummary:
    def test_chapter_summary_with_many_turns(self):
        summaries = []
        for i in range(10):
            summaries.append({
                "turn_number": i + 1,
                "user_intent": f"用户意图{i}",
                "assistant_action": f"助手操作{i}",
                "result_summary": f"结果{i}",
                "files_touched": [f"file{i}.py"] if i % 2 == 0 else [],
            })
        result = summarize_chapter(summaries)
        assert "10" in result["summary"] or "完成" in result["summary"]
        assert len(result["key_files"]) <= 10

    def test_chapter_summary_empty(self):
        result = summarize_chapter([])
        assert result["summary"]


class TestFileChangeLog:
    def test_multiple_file_changes(self):
        state = ConversationState()
        changes = [
            {"name": "write_file", "args": {"file_path": "src/app.py"}},
            {"name": "patch", "args": {"path": "src/utils.py"}},
            {"name": "write_file", "args": {"file_path": "src/models.py"}},
        ]
        for i, tc in enumerate(changes):
            file_changes = _extract_file_changes([tc])
            for fc in file_changes:
                if fc["path"]:
                    state.add_file_change(
                        path=fc["path"],
                        operation=fc["operation"],
                        description=fc["description"],
                        turn_number=i + 1,
                    )
        assert len(state.file_change_log) == 3
        assert state.file_change_log[0].path == "src/app.py"
        assert state.file_change_log[1].path == "src/utils.py"

    def test_file_change_log_rolling(self):
        state = ConversationState()
        for i in range(60):
            state.add_file_change(
                path=f"file{i}.py",
                operation="write",
                description=f"创建文件{i}",
                turn_number=i + 1,
            )
        assert len(state.file_change_log) == 50
        assert state.file_change_log[0].path == "file10.py"


class TestTaskTreeDeepNesting:
    def test_deep_nested_tasks(self):
        state = ConversationState()
        state.add_task(task_id="proj", title="项目")
        state.add_task(task_id="milestone1", title="里程碑1", parent_id="proj")
        state.add_task(task_id="task1", title="任务1", parent_id="milestone1")
        state.add_task(task_id="subtask1", title="子任务1", parent_id="task1")
        assert state.task_tree is not None
        assert len(state.task_tree.children) == 1
        assert state.task_tree.children[0].title == "项目"
        assert len(state.task_tree.children[0].children) == 1
        assert state.task_tree.children[0].children[0].title == "里程碑1"
        assert len(state.task_tree.children[0].children[0].children) == 1
        assert state.task_tree.children[0].children[0].children[0].title == "任务1"
        assert len(state.task_tree.children[0].children[0].children[0].children) == 1
        assert state.task_tree.children[0].children[0].children[0].children[0].title == "子任务1"

    def test_task_tree_serialization(self):
        state = ConversationState()
        state.add_task(task_id="task1", title="测试任务", status="completed")
        state.add_task(task_id="task2", title="子任务", parent_id="task1")
        data = state.to_full_state()
        assert data["task_tree"] is not None
        assert data["task_tree"]["children"][0]["title"] == "测试任务"
        assert len(data["task_tree"]["children"][0]["children"]) == 1


class TestLongConversationScenario:
    def test_20_turn_conversation_state(self):
        state = ConversationState()
        state.update_conversation_goal("开发一个电商平台")
        state.update_task_summary("完成商品管理模块")

        for turn in range(1, 21):
            if turn == 1:
                intent = "创建项目结构"
                action = "创建目录结构和基础文件"
                files = ["app.py", "models/__init__.py"]
            elif turn == 5:
                intent = "实现商品模型"
                action = "创建 Product 模型"
                files = ["models/product.py"]
                state.add_decision(turn, "使用 SQLAlchemy ORM", "成熟稳定")
            elif turn == 10:
                intent = "实现商品API"
                action = "创建商品 CRUD 接口"
                files = ["api/product.py"]
            elif turn == 15:
                intent = "添加图片上传"
                action = "集成文件上传功能"
                files = ["utils/upload.py"]
            elif turn == 20:
                intent = "测试商品模块"
                action = "编写单元测试"
                files = ["tests/test_product.py"]
            else:
                intent = f"继续开发第{turn}步"
                action = f"执行开发任务{turn}"
                files = []

            state.add_turn_summary(turn, intent, action, "完成", files)

            if turn % 10 == 0:
                summaries_data = [
                    {"turn_number": ts.turn_number, "user_intent": ts.user_intent,
                     "assistant_action": ts.assistant_action, "result_summary": ts.result_summary,
                     "files_touched": ts.files_touched}
                    for ts in state.turn_summaries
                    if (turn - 9) <= ts.turn_number <= turn
                ]
                chapter_result = summarize_chapter(summaries_data)
                state.add_chapter_summary(
                    chapter_number=turn // 10,
                    start_turn=turn - 9,
                    end_turn=turn,
                    summary=chapter_result["summary"],
                    key_decisions=chapter_result["key_decisions"],
                    key_files=chapter_result["key_files"],
                )

        assert len(state.turn_summaries) == 20
        assert len(state.chapter_summaries) == 2
        assert len(state.decisions_made) == 1

        reminder = state.to_system_reminder()
        assert "开发一个电商平台" in reminder
        assert "商品管理模块" in reminder

        compact = state.to_compact_anchor()
        assert "开发一个电商平台" in compact

    def test_token_budget_priority(self):
        state = ConversationState()
        state.update_conversation_goal("重要的对话目标")
        state.update_task_summary("重要的当前任务")
        for i in range(20):
            state.add_plan_step(f"不太重要的计划步骤{i}")
        for i in range(30):
            state.add_decision(i + 1, f"不太重要的决策{i}", "理由")

        reminder = state.to_system_reminder(token_budget=500)
        assert "重要的对话目标" in reminder
        assert "重要的当前任务" in reminder


@pytest.mark.skipif(
    not os.getenv("DEEPSEEK_API_KEY") and not os.getenv("MINIMAX_API_KEY"),
    reason="No LLM API key available"
)
class TestRealLLMMultiTurn:
    def test_llm_chapter_summary(self):
        summaries = []
        for i in range(5):
            summaries.append({
                "turn_number": i + 1,
                "user_intent": f"用户想要创建一个Python应用，第{i+1}步",
                "assistant_action": f"助手创建了文件并实现了功能，第{i+1}步",
                "result_summary": "成功完成",
                "files_touched": ["app.py", "utils.py", "tests/test_app.py"],
            })
        result = summarize_chapter(summaries)
        assert len(result["summary"]) > 20
        assert result["key_files"]