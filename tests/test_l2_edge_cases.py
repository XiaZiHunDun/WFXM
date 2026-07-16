"""L2 Edge Case Tests — ~50 tests for boundary conditions and edge cases.

These tests cover extreme inputs, empty states, overflow scenarios, and unusual
combinations. Run before merge.
"""

import pytest

from butler.core.conversation_state import ConversationState


@pytest.mark.l2
class TestEmptyStateEdgeCases:
    def test_add_turn_summary_to_empty_state(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(1, "意图", "操作", "结果")
        assert len(state.turn_summaries) == 1

    def test_add_decision_to_empty_state(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_decision(1, "决策", "理由")
        assert len(state.decisions_made) == 1

    def test_add_chapter_summary_to_empty_state(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_chapter_summary(1, 1, 10, "摘要")
        assert len(state.chapter_summaries) == 1

    def test_empty_turn_summary_fields(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(1, "", "", "")
        assert len(state.turn_summaries) == 1
        assert state.turn_summaries[0].user_intent == ""

    def test_empty_decision_fields(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_decision(1, "", "")
        assert len(state.decisions_made) == 1
        assert state.decisions_made[0].decision == ""

    def test_empty_file_change_fields(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_file_change("", "", "", 1)
        assert len(state.file_change_log) == 1
        assert state.file_change_log[0].path == ""


@pytest.mark.l2
class TestOverflowEdgeCases:
    def test_turn_summaries_exact_max_then_one_more(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(20):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
        assert len(state.turn_summaries) == 20
        state.add_turn_summary(21, "意图21", "操作21", "完成")
        assert len(state.turn_summaries) == 20
        assert state.turn_summaries[0].turn_number == 2

    def test_decisions_exact_max_then_one_more(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(30):
            state.add_decision(i + 1, f"决策{i}", "理由")
        assert len(state.decisions_made) == 30
        state.add_decision(31, "决策31", "理由")
        assert len(state.decisions_made) == 30
        assert state.decisions_made[0].turn_number == 2

    def test_file_changes_exact_max_then_one_more(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(50):
            state.add_file_change(f"file_{i}.py", "write", "描述", i + 1)
        assert len(state.file_change_log) == 50
        state.add_file_change("file_50.py", "write", "描述", 51)
        assert len(state.file_change_log) == 50
        assert state.file_change_log[0].path == "file_1.py"

    def test_chapters_exact_max_then_one_more(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(10):
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
        assert len(state.chapter_summaries) == 10
        state.add_chapter_summary(11, 101, 110, "章节11")
        assert len(state.chapter_summaries) == 10
        assert state.chapter_summaries[0].chapter_number == 2


@pytest.mark.l2
class TestExtremeInputEdgeCases:
    def test_extremely_long_user_intent(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_text = "X" * 10000
        state.add_turn_summary(1, long_text, "操作", "结果")
        assert len(state.turn_summaries[0].user_intent) == 500

    def test_extremely_long_decision_rationale(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_text = "X" * 10000
        state.add_decision(1, "决策", long_text)
        assert len(state.decisions_made[0].rationale) == 500

    def test_extremely_long_chapter_summary(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_text = "X" * 10000
        state.add_chapter_summary(1, 1, 10, long_text)
        assert len(state.chapter_summaries[0].summary) == 1000

    def test_extremely_long_file_path(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        long_path = "/".join(["a" * 100] * 20)
        state.add_file_change(long_path, "write", "描述", 1)
        assert state.file_change_log[0].path == long_path

    def test_unicode_characters(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(1, "中文测试测试测试", "操作", "结果")
        assert "中文" in state.turn_summaries[0].user_intent

    def test_emoji_and_special_chars(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(1, "测试🎉🔥✨", "操作", "结果")
        assert "🎉" in state.turn_summaries[0].user_intent


@pytest.mark.l2
class TestNegativeEdgeCases:
    def test_zero_turn_number(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(0, "意图", "操作", "结果")
        assert state.turn_summaries[0].turn_number == 0

    def test_negative_turn_number(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(-1, "意图", "操作", "结果")
        assert state.turn_summaries[0].turn_number == -1

    def test_out_of_order_turns(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_turn_summary(5, "意图5", "操作5", "完成")
        state.add_turn_summary(1, "意图1", "操作1", "完成")
        state.add_turn_summary(3, "意图3", "操作3", "完成")
        assert len(state.turn_summaries) == 3
        assert state.turn_summaries[0].turn_number == 5
        assert state.turn_summaries[1].turn_number == 1
        assert state.turn_summaries[2].turn_number == 3


@pytest.mark.l2
class TestMemoryPressureEdgeCases:
    def test_rapid_state_filling_and_empty(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        
        for i in range(100):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
        
        assert len(state.turn_summaries) == 20
        
        state.reset()
        assert len(state.turn_summaries) == 0
        assert state.is_empty is True

    def test_simultaneous_multiple_type_filling(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        
        for i in range(100):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
            state.add_decision(i + 1, f"决策{i}", "理由{i}")
            state.add_file_change(f"file_{i}.py", "write", "描述{i}", i + 1)
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
            state.add_plan_step(f"步骤{i}")
            state.add_open_question(f"问题{i}")
        
        assert len(state.turn_summaries) == 20
        assert len(state.decisions_made) == 30
        assert len(state.file_change_log) == 50
        assert len(state.chapter_summaries) == 10
        assert len(state.current_plan_steps) == 20
        assert len(state.open_questions) == 15


@pytest.mark.l2
class TestToolIntegrationEdgeCases:
    def test_load_nonexistent_state(self):
        from butler.tools.conversation_state_tools import load_conversation_state, _STATE_FILE
        
        if _STATE_FILE.exists():
            _STATE_FILE.unlink()
        
        result = load_conversation_state()
        assert result is None

    def test_update_nonexistent_task(self, empty_conversation_state: ConversationState):
        result = empty_conversation_state.update_task_status("nonexistent", "completed")
        assert result is False

    def test_find_nonexistent_task(self, empty_conversation_state: ConversationState):
        result = empty_conversation_state.find_task_by_id("nonexistent")
        assert result is None

    def test_resolve_nonexistent_question(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_open_question("存在的问题")
        state.resolve_open_question("不存在的问题")
        assert len(state.open_questions) == 1

    def test_remove_nonexistent_plan_step(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_plan_step("存在的步骤")
        state.remove_plan_step("不存在的步骤")
        assert len(state.current_plan_steps) == 1

    def test_remove_nonexistent_todo(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        state.add_pending_todo("存在的todo")
        state.remove_pending_todo("不存在的todo")
        assert len(state.pending_todos) == 1


@pytest.mark.l2
class TestTokenBudgetEdgeCases:
    def test_zero_token_budget(self, populated_conversation_state: ConversationState):
        reminder = populated_conversation_state.to_system_reminder(token_budget=0)
        assert reminder == "" or len(reminder) < 100

    def test_extremely_large_token_budget(self, full_conversation_state: ConversationState):
        reminder = full_conversation_state.to_system_reminder(token_budget=100000)
        assert len(reminder) > 0

    def test_overflow_token_budget(self, full_conversation_state: ConversationState):
        reminder = full_conversation_state.to_system_reminder(token_budget=-1)
        assert len(reminder) > 0


@pytest.mark.l2
class TestStateSerializationEdgeCases:
    def test_empty_state_serialization(self, empty_conversation_state: ConversationState):
        data = empty_conversation_state.to_full_state()
        assert data["conversation_goal"] == ""
        assert data["turn_summaries"] == []
        assert data["task_tree"] is None

    def test_full_state_with_empty_task_tree(self, populated_conversation_state: ConversationState):
        data = populated_conversation_state.to_full_state()
        assert data["task_tree"] is None

    def test_state_with_max_everything(self, full_conversation_state: ConversationState):
        data = full_conversation_state.to_full_state()
        assert len(data["turn_summaries"]) == 20
        assert len(data["decisions_made"]) == 30
        assert len(data["file_change_log"]) == 50
        assert len(data["chapter_summaries"]) == 10


@pytest.mark.l2
class TestTurnSummarizerEdgeCases:
    def test_summarize_turn_with_empty_inputs(self):
        from butler.core.turn_summarizer import summarize_turn
        
        result = summarize_turn("", "", [])
        assert isinstance(result, dict)
        assert result["user_intent"] == ""

    def test_summarize_chapter_with_empty_list(self):
        from butler.core.turn_summarizer import summarize_chapter
        
        result = summarize_chapter([])
        assert isinstance(result, dict)
        assert len(result["summary"]) > 0

    def test_extract_file_changes_with_empty_list(self):
        from butler.core.turn_summarizer import _extract_file_changes
        
        result = _extract_file_changes([])
        assert result == []

    def test_extract_file_changes_with_none(self):
        from butler.core.turn_summarizer import _extract_file_changes
        
        result = _extract_file_changes(None)
        assert result == []

    def test_extract_file_changes_with_invalid_tool_call(self):
        from butler.core.turn_summarizer import _extract_file_changes
        
        result = _extract_file_changes([{"name": "unknown_tool", "args": {}}])
        assert len(result) == 1 or result == []
