"""Conversational tests — memory system depth.

Tests correct routing between butler_remember (preferences/experience)
and butler_recall (retrieval), including scope selection, negative
cases, and mixed memory+action scenarios.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_memory.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestRememberPreferences:
    """Personal preference → butler_remember(owner_profile)."""

    def test_remember_coffee(self, live_minimax_handler):
        """'记住我喜欢喝美式'."""
        result = send_message(
            live_minimax_handler,
            "记住我喜欢喝美式咖啡",
            rubric=ConversationRubric(expect_tool_called="butler_remember"),
        )
        assert_turn_passed(result)

    def test_remember_food_allergy(self, live_minimax_handler):
        """'我不吃海鲜，记住了'."""
        result = send_message(
            live_minimax_handler,
            "我不吃海鲜，记住了",
            rubric=ConversationRubric(expect_tool_called="butler_remember"),
        )
        assert_turn_passed(result)

    def test_remember_nickname(self, live_minimax_handler):
        """'以后叫我老板'."""
        result = send_message(
            live_minimax_handler,
            "以后叫我老板就行",
            rubric=ConversationRubric(expect_tool_called="butler_remember"),
        )
        assert_turn_passed(result)


class TestRememberExperience:
    """Work experience → butler_remember(owner_experience)."""

    def test_remember_tech_lesson(self, live_minimax_handler):
        """Technical lesson learned."""
        result = send_message(
            live_minimax_handler,
            "总结一下：微信开发要注意消息幂等性",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember"],
            ),
        )
        assert_turn_passed(result)


class TestRememberProjectNotes:
    """Project decisions → butler_remember(project_notes)."""

    def test_remember_project_decision(self, lingwen_handler):
        """Project-specific decision."""
        result = send_message(
            lingwen_handler,
            "灵文项目决定用 markdown 格式写文档",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember"],
            ),
        )
        assert_turn_passed(result)


class TestRecall:
    """butler_recall for retrieving stored memory."""

    def test_recall_preference(self, live_minimax_handler):
        """'我之前说喜欢喝什么来着'."""
        result = send_message(
            live_minimax_handler,
            "我之前说喜欢喝什么来着",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_recall"],
            ),
        )
        assert_turn_passed(result)

    def test_recall_experience(self, live_minimax_handler):
        """'我之前总结过什么经验'."""
        result = send_message(
            live_minimax_handler,
            "我之前总结过什么经验",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_recall"],
            ),
        )
        assert_turn_passed(result)

    def test_vague_recall(self, live_minimax_handler):
        """'我之前跟你说过什么'."""
        result = send_message(
            live_minimax_handler,
            "我之前跟你说过什么",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_recall"],
            ),
        )
        assert_turn_passed(result)


class TestNoRemember:
    """Inputs that should NOT trigger butler_remember."""

    def test_casual_weather(self, live_minimax_handler):
        """'今天天气真好' — should not remember."""
        result = send_message(
            live_minimax_handler,
            "今天天气真好",
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        called = [e["tool"] for e in result.tool_events if e.get("ok")]
        assert "butler_remember" not in called, (
            f"Should not remember casual chat, but called: {called}"
        )
        assert_turn_passed(result)

    def test_opinion_question(self, live_minimax_handler):
        """'你觉得呢' — should not remember."""
        result = send_message(
            live_minimax_handler,
            "你觉得呢",
            rubric=ConversationRubric(reject_keywords=["error"]),
        )
        called = [e["tool"] for e in result.tool_events if e.get("ok")]
        assert "butler_remember" not in called
        assert_turn_passed(result)

    def test_dont_remember(self, live_minimax_handler):
        """'上面说的别记了' — explicit no-remember."""
        result = send_message(
            live_minimax_handler,
            "上面说的不用记了",
            rubric=ConversationRubric(reject_keywords=["error"]),
        )
        called = [e["tool"] for e in result.tool_events if e.get("ok")]
        assert "butler_remember" not in called
        assert_turn_passed(result)


class TestMemoryMixedAction:
    """Combined memory + action scenarios."""

    def test_remember_plus_memo(self, live_minimax_handler):
        """'记住我爱吃火锅，帮我约个这周六的火锅'."""
        result = send_message(
            live_minimax_handler,
            "记住我爱吃火锅，帮我约个这周六去吃火锅",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_contact_not_recall(self, live_minimax_handler):
        """'我之前存过张三的电话吗' → contact_find, not recall."""
        result = send_message(
            live_minimax_handler,
            "我之前存过张三的电话吗",
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_find", "butler_recall"],
            ),
        )
        assert_turn_passed(result)
