"""Conversational tests — reminder system.

Tests the set_reminder / list_reminders / cancel_reminder tools
and the disambiguation between reminder and memo.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_reminder.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestSetReminder:
    """Creating reminders."""

    def test_relative_time_reminder(self, live_minimax_handler):
        """'一小时后提醒我喝水'."""
        result = send_message(
            live_minimax_handler,
            "一小时后提醒我喝水",
            rubric=ConversationRubric(
                expect_any_tool_called=["set_reminder", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_absolute_time_reminder(self, live_minimax_handler):
        """'明天早上9点提醒我打电话'."""
        result = send_message(
            live_minimax_handler,
            "明天早上9点提醒我打电话",
            rubric=ConversationRubric(
                expect_any_tool_called=["set_reminder", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_recurring_reminder(self, live_minimax_handler):
        """'每天下午3点提醒我喝水'."""
        result = send_message(
            live_minimax_handler,
            "每天下午3点提醒我喝水",
            rubric=ConversationRubric(
                expect_any_tool_called=["set_reminder", "habit_create", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_vague_time_reminder(self, live_minimax_handler):
        """'过一会儿提醒我' — vague time."""
        result = send_message(
            live_minimax_handler,
            "过一会儿提醒我看邮件",
            rubric=ConversationRubric(
                expect_any_tool_called=["set_reminder", "memo_add"],
            ),
        )
        assert_turn_passed(result)


class TestListAndCancelReminder:
    """Querying and cancelling reminders."""

    def test_list_reminders(self, live_minimax_handler):
        """'我有什么提醒'."""
        result = send_message(
            live_minimax_handler,
            "我有什么提醒",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_reminders", "memo_list"],
            ),
        )
        assert_turn_passed(result)

    def test_cancel_reminder(self, live_minimax_handler):
        """'取消喝水的提醒'."""
        result = send_message(
            live_minimax_handler,
            "取消喝水的提醒",
            rubric=ConversationRubric(
                expect_any_tool_called=["cancel_reminder", "memo_delete"],
            ),
        )
        assert_turn_passed(result)

    def test_check_empty_reminders(self, live_minimax_handler):
        """'看看有没有提醒' — empty list."""
        result = send_message(
            live_minimax_handler,
            "看看有没有什么提醒",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_reminders", "memo_list"],
            ),
        )
        assert_turn_passed(result)


class TestReminderVsMemo:
    """Disambiguation between reminder and memo."""

    def test_dont_forget_is_memo(self, live_minimax_handler):
        """'别忘了明天交报告' → memo_add (task, not timer)."""
        result = send_message(
            live_minimax_handler,
            "别忘了明天交报告",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add", "set_reminder"],
            ),
        )
        assert_turn_passed(result)

    def test_remind_with_time_is_both(self, live_minimax_handler):
        """'提醒我明天3点交报告' — could be memo + reminder."""
        result = send_message(
            live_minimax_handler,
            "提醒我明天3点交报告",
            rubric=ConversationRubric(
                expect_any_tool_called=["set_reminder", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_cancel_nonexistent(self, live_minimax_handler):
        """Cancel something that doesn't exist — friendly feedback."""
        result = send_message(
            live_minimax_handler,
            "取消一个不存在的提醒",
            rubric=ConversationRubric(
                reject_keywords=["traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)
