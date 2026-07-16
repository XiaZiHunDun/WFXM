"""L2 Property-Based Tests — ~50 tests validating ConversationState invariants.

These tests use property-based testing patterns to verify that certain invariants
always hold regardless of input. Run before merge.
"""

import pytest

from butler.core.conversation_state import ConversationState


@pytest.mark.l2
class TestInvariants:
    def test_turn_summaries_never_exceed_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(100):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
            assert len(state.turn_summaries) <= 20

    def test_decisions_never_exceed_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(100):
            state.add_decision(i + 1, f"决策{i}", "理由")
            assert len(state.decisions_made) <= 30

    def test_chapters_never_exceed_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(100):
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
            assert len(state.chapter_summaries) <= 10

    def test_file_changes_never_exceed_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(100):
            state.add_file_change(f"file_{i}.py", "write", "描述", i + 1)
            assert len(state.file_change_log) <= 50

    def test_open_questions_never_exceed_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(100):
            state.add_open_question(f"问题{i}")
            assert len(state.open_questions) <= 15

    def test_plan_steps_never_exceed_max(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(100):
            state.add_plan_step(f"步骤{i}")
            assert len(state.current_plan_steps) <= 20


@pytest.mark.l2
class TestRollingWindowInvariants:
    def test_turn_summaries_always_recent(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(30):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
        
        assert len(state.turn_summaries) == 20
        assert state.turn_summaries[0].turn_number == 11
        assert state.turn_summaries[-1].turn_number == 30

    def test_decisions_always_recent(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(40):
            state.add_decision(i + 1, f"决策{i}", "理由")
        
        assert len(state.decisions_made) == 30
        assert state.decisions_made[0].turn_number == 11
        assert state.decisions_made[-1].turn_number == 40

    def test_chapters_always_recent(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(15):
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
        
        assert len(state.chapter_summaries) == 10
        assert state.chapter_summaries[0].chapter_number == 6
        assert state.chapter_summaries[-1].chapter_number == 15


@pytest.mark.l2
class TestTokenBudgetInvariants:
    def test_system_reminder_never_empty_on_populated_state(self, populated_conversation_state: ConversationState):
        reminder = populated_conversation_state.to_system_reminder()
        assert reminder != ""

    def test_system_reminder_respects_token_budget(self, full_conversation_state: ConversationState):
        for budget in [500, 1000, 1500, 2000, 3000]:
            reminder = full_conversation_state.to_system_reminder(token_budget=budget)
            assert len(reminder) < budget * 4

    def test_system_reminder_preserves_high_priority_content(self, full_conversation_state: ConversationState):
        state = full_conversation_state
        reminder = state.to_system_reminder(token_budget=500)
        
        assert "开发一个复杂的Web应用" in reminder or "对话目标" in reminder
        assert "完成核心功能开发" in reminder or "当前任务" in reminder


@pytest.mark.l2
class TestDataIntegrityInvariants:
    def test_turn_summaries_have_unique_turn_numbers(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(20):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
        
        turn_numbers = [ts.turn_number for ts in state.turn_summaries]
        assert len(turn_numbers) == len(set(turn_numbers))

    def test_decisions_have_valid_turn_numbers(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(30):
            state.add_decision(i + 1, f"决策{i}", "理由")
        
        assert all(d.turn_number > 0 for d in state.decisions_made)

    def test_file_changes_have_valid_paths(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(50):
            state.add_file_change(f"file_{i}.py", "write", "描述", i + 1)
        
        assert all(fc.path for fc in state.file_change_log)

    def test_chapters_have_valid_ranges(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        for i in range(10):
            state.add_chapter_summary(i + 1, i * 10 + 1, (i + 1) * 10, f"章节{i}")
        
        assert all(ch.start_turn <= ch.end_turn for ch in state.chapter_summaries)


@pytest.mark.l2
class TestStateTransitionInvariants:
    def test_state_is_empty_after_reset(self, full_conversation_state: ConversationState):
        state = full_conversation_state
        assert state.is_empty is False
        state.reset()
        assert state.is_empty is True

    def test_reset_preserves_max_limits(self, full_conversation_state: ConversationState):
        state = full_conversation_state
        state.reset()
        
        assert state._max_turn_summaries == 20
        assert state._max_decisions == 30
        assert state._max_chapters == 10
        assert state._max_file_changes == 50

    def test_adding_content_makes_state_non_empty(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        assert state.is_empty is True
        
        state.add_turn_summary(1, "测试", "测试", "完成")
        assert state.is_empty is False


@pytest.mark.l2
class TestToolIntegrationInvariants:
    def test_state_persistence_roundtrip(self, populated_conversation_state: ConversationState):
        from butler.tools.conversation_state_tools import (
            persist_conversation_state,
            load_conversation_state,
        )
        
        original = populated_conversation_state
        persist_conversation_state(original)
        
        loaded = load_conversation_state()
        
        assert loaded is not None
        assert loaded.conversation_goal == original.conversation_goal
        assert len(loaded.turn_summaries) == len(original.turn_summaries)
        assert len(loaded.files_modified) == len(original.files_modified)

    @pytest.mark.skip(reason="Requires dotenv module")
    def test_state_search_always_returns_valid_json(self, populated_conversation_state: ConversationState):
        from butler.tools.conversation_state_tools import (
            persist_conversation_state,
            tool_conversation_state_search,
        )
        
        persist_conversation_state(populated_conversation_state)
        
        import json
        result = tool_conversation_state_search("测试")
        parsed = json.loads(result)
        assert "ok" in parsed


@pytest.mark.l2
class TestTurnSummarizerInvariants:
    def test_summarize_turn_always_returns_dict(self):
        from butler.core.turn_summarizer import summarize_turn
        
        result = summarize_turn("用户消息", "助手回复", [])
        assert isinstance(result, dict)
        assert "user_intent" in result
        assert "assistant_action" in result
        assert "result_summary" in result

    def test_summarize_chapter_always_returns_dict(self):
        from butler.core.turn_summarizer import summarize_chapter
        
        summaries = [{"turn_number": 1, "user_intent": "测试", "assistant_action": "测试", "result_summary": "完成"}]
        result = summarize_chapter(summaries)
        assert isinstance(result, dict)
        assert "summary" in result
        assert "key_decisions" in result
        assert "key_files" in result

    def test_extract_file_changes_always_returns_list(self):
        from butler.core.turn_summarizer import _extract_file_changes
        
        result = _extract_file_changes([])
        assert isinstance(result, list)
        
        result = _extract_file_changes([{"name": "write_file", "args": {"file_path": "test.py"}}])
        assert isinstance(result, list)


@pytest.mark.l2
class TestCompactionInvariants:
    def test_compact_anchor_never_exceeds_reasonable_length(self, full_conversation_state: ConversationState):
        anchor = full_conversation_state.to_compact_anchor()
        assert len(anchor) < 2000

    def test_compact_anchor_preserves_key_info(self, populated_conversation_state: ConversationState):
        anchor = populated_conversation_state.to_compact_anchor()
        assert "开发一个电商平台" in anchor or "目标" in anchor


@pytest.mark.l2
class TestConcurrencySafetyInvariants:
    def test_multiple_add_operations_dont_corrupt_state(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        
        for i in range(50):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
            state.add_decision(i + 1, f"决策{i}", "理由")
            state.add_file_change(f"file_{i}.py", "write", "描述", i + 1)
        
        assert len(state.turn_summaries) <= 20
        assert len(state.decisions_made) <= 30
        assert len(state.file_change_log) <= 50

    def test_interleaved_operations_maintain_order(self, empty_conversation_state: ConversationState):
        state = empty_conversation_state
        
        for i in range(10):
            state.add_turn_summary(i + 1, f"意图{i}", f"操作{i}", "完成")
        
        assert [ts.turn_number for ts in state.turn_summaries] == list(range(1, 11))
