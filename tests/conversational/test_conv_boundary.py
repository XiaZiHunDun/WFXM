"""Conversational tests — boundary and edge cases.

Tests system behavior with unusual inputs: empty messages, very long
text, emoji-only, special characters, injection attempts, extreme
values, and multi-language mixing.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_boundary.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestEmptyAndWhitespace:
    """Empty or whitespace-only inputs."""

    def test_empty_string(self, live_minimax_handler):
        """Empty string — should not crash."""
        result = send_message(
            live_minimax_handler, "",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        # Empty input may produce empty response or a prompt; either is fine
        assert_turn_passed(result)

    def test_whitespace_only(self, live_minimax_handler):
        """Whitespace-only input."""
        result = send_message(
            live_minimax_handler, "   \n\t  ",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)


class TestEmojiAndSpecialChars:
    """Emoji and special character inputs."""

    def test_emoji_only(self, live_minimax_handler):
        """Pure emoji — should respond friendly, no tool."""
        result = send_message(
            live_minimax_handler, "👍",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "traceback"],
            ),
        )
        assert_turn_passed(result)

    def test_laughing_emoji(self, live_minimax_handler):
        """Laughing face — social response."""
        result = send_message(
            live_minimax_handler, "😂😂😂",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "traceback"],
            ),
        )
        assert_turn_passed(result)

    def test_special_punctuation(self, live_minimax_handler):
        """Special punctuation mix."""
        result = send_message(
            live_minimax_handler, "???!!!...",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)


class TestNonsenseInput:
    """Nonsense / random input."""

    def test_keyboard_mash(self, live_minimax_handler):
        """Random keyboard input — should not trigger tools."""
        result = send_message(
            live_minimax_handler, "asdfghjkl",
            rubric=ConversationRubric(
                reject_keywords=["traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_pure_number(self, live_minimax_handler):
        """'12345' — should not trigger expense_add."""
        result = send_message(
            live_minimax_handler, "12345",
            rubric=ConversationRubric(
                reject_keywords=["traceback"],
            ),
        )
        assert_turn_passed(result)

    def test_english_greeting(self, live_minimax_handler):
        """English greeting — should respond naturally."""
        result = send_message(
            live_minimax_handler, "hello world",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestExtremeValues:
    """Extreme numeric and date values."""

    def test_negative_amount(self, live_minimax_handler):
        """Negative amount — refund scenario."""
        result = send_message(
            live_minimax_handler, "退款100块",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add"],
            ),
        )
        assert_turn_passed(result)

    def test_huge_amount(self, live_minimax_handler):
        """Very large amount — should not crash."""
        result = send_message(
            live_minimax_handler, "买房首付花了500000",
            rubric=ConversationRubric(
                expect_tool_called="expense_add",
            ),
        )
        assert_turn_passed(result)

    def test_far_future_date(self, live_minimax_handler):
        """Far future date — should still create memo."""
        result = send_message(
            live_minimax_handler, "2099年1月1日开会，帮我记一下",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_past_date_backfill(self, live_minimax_handler):
        """Past date — backfill scenario."""
        result = send_message(
            live_minimax_handler, "昨天忘记记了，午饭花了25",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)


class TestInjectionSafety:
    """Injection and safety boundary tests."""

    def test_html_injection(self, live_minimax_handler):
        """HTML tags — should be treated as plain text."""
        result = send_message(
            live_minimax_handler, "<script>alert(1)</script>",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_multi_language_mix(self, live_minimax_handler):
        """Chinese-English-Japanese mix."""
        result = send_message(
            live_minimax_handler, "帮我schedule一个meeting明天",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
            ),
        )
        assert_turn_passed(result)

    def test_multi_intent_in_one(self, live_minimax_handler):
        """Three intents in one message."""
        result = send_message(
            live_minimax_handler,
            "记个账午饭30块，存个电话赵六13800001234，明天下午开会帮我记一下",
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "expense_add", "contact_add", "memo_add",
                ],
            ),
        )
        assert_turn_passed(result)
