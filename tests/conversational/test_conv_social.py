"""Conversational tests — emotional and social interaction.

Tests that the butler responds naturally to emotional and social
messages without inappropriately triggering tools.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_social.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestGreetings:
    """Time-based greetings."""

    def test_good_morning(self, live_minimax_handler):
        """Morning greeting."""
        result = send_message(
            live_minimax_handler, "早上好",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_good_night(self, live_minimax_handler):
        """Night greeting."""
        result = send_message(
            live_minimax_handler, "晚安",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestGratitude:
    """Thank you messages."""

    def test_big_thanks(self, live_minimax_handler):
        """Enthusiastic thanks."""
        result = send_message(
            live_minimax_handler, "太感谢了，帮了大忙",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestComplaints:
    """Complaint and frustration."""

    def test_slow_complaint(self, live_minimax_handler):
        """'怎么这么慢啊'."""
        result = send_message(
            live_minimax_handler, "怎么这么慢啊",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_self_deprecation(self, live_minimax_handler):
        """'我记性太差了'."""
        result = send_message(
            live_minimax_handler, "我记性太差了",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestPraiseAndEncouragement:
    """Praise and positive feedback."""

    def test_praise(self, live_minimax_handler):
        """'你做得真好'."""
        result = send_message(
            live_minimax_handler, "你做得真好",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestEmotionalSupport:
    """Emotional messages that need empathetic responses."""

    def test_bad_mood(self, live_minimax_handler):
        """'今天心情不好'."""
        result = send_message(
            live_minimax_handler, "今天心情不好",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_overwhelmed(self, live_minimax_handler):
        """'事情太多忙不过来' — might suggest tools."""
        result = send_message(
            live_minimax_handler, "事情太多忙不过来",
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestCasualChat:
    """Casual conversation that should not trigger tools."""

    def test_teasing(self, live_minimax_handler):
        """'你是不是偷懒了'."""
        result = send_message(
            live_minimax_handler, "你是不是偷懒了",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_trust_building(self, live_minimax_handler):
        """'你能帮我管好这些事吗'."""
        result = send_message(
            live_minimax_handler, "你能帮我管好这些事吗",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)
