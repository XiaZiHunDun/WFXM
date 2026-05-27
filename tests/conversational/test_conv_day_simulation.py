"""Conversational tests — one-day life scenario simulation.

Simulates a real person's typical day of interactions with the butler,
from morning routines through work to evening wind-down. All 15 turns
use the same session key to test context retention across a full day.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_day_simulation.py -v
"""

from __future__ import annotations

import logging

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import (
    ConversationRubric,
    TurnResult,
    assert_turn_passed,
    format_report,
)

logger = logging.getLogger(__name__)

SK = "wechat:day-sim"


class TestMorningRoutine:
    """Morning interactions: checkin, schedule, prep."""

    def test_morning_checkin(self, live_minimax_handler):
        """'早起打卡' → habit_checkin."""
        send_message(
            live_minimax_handler, "帮我创建一个早起打卡的习惯",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler, "早起打卡",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_checkin"],
            ),
        )
        assert_turn_passed(result)

    def test_check_schedule(self, live_minimax_handler):
        """'今天有什么安排' → memo_list."""
        result = send_message(
            live_minimax_handler, "今天有什么安排",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
            ),
        )
        assert_turn_passed(result)

    def test_general_question(self, live_minimax_handler):
        """'我钥匙放哪了' → recall or general answer."""
        result = send_message(
            live_minimax_handler, "我钥匙通常放哪里",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_recall"],
                reject_keywords=["error"],
            ),
        )
        assert_turn_passed(result)


class TestWorkMorning:
    """Morning work: switch project, check status, delegate."""

    def test_switch_to_work(self, lingwen_handler):
        """'切换到灵文项目'."""
        result = send_message(
            lingwen_handler, "切换到灵文1号",
            session_key="wechat:day-sim-dev",
            rubric=ConversationRubric(expect_keywords=["已切换"]),
        )
        assert_turn_passed(result)

    def test_check_yesterday(self, lingwen_handler):
        """'昨天改了什么'."""
        result = send_message(
            lingwen_handler, "看看项目有什么文件",
            session_key="wechat:day-sim-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory", "read_file"],
            ),
        )
        assert_turn_passed(result)

    def test_delegate_test(self, lingwen_handler):
        """'让开发代理跑一下测试'."""
        result = send_message(
            lingwen_handler, "让开发代理检查一下代码",
            session_key="wechat:day-sim-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "list_directory"],
            ),
        )
        assert_turn_passed(result)


class TestLunchtime:
    """Lunchtime: expense tracking."""

    def test_lunch_expense(self, live_minimax_handler):
        """'午饭团购25'."""
        result = send_message(
            live_minimax_handler, "午饭团购25",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)


class TestAfternoon:
    """Afternoon: contacts, reminders, meeting notes."""

    def test_save_colleague(self, live_minimax_handler):
        """'新同事小王 13512345678'."""
        result = send_message(
            live_minimax_handler, "存一下新同事小王 13512345678",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(result)

    def test_meeting_reminder(self, live_minimax_handler):
        """'3点开会别忘了'."""
        result = send_message(
            live_minimax_handler, "3点开会别忘了",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add", "set_reminder"],
            ),
        )
        assert_turn_passed(result)

    def test_meeting_note(self, live_minimax_handler):
        """'记一下会议决定：下周发版'."""
        result = send_message(
            live_minimax_handler, "记住会议决定：下周发版",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember", "memo_add"],
            ),
        )
        assert_turn_passed(result)


class TestEvening:
    """Evening: commute expense, daily summary, planning."""

    def test_commute_expense(self, live_minimax_handler):
        """'下班打车回家38'."""
        result = send_message(
            live_minimax_handler, "下班打车回家38",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)

    def test_daily_spending(self, live_minimax_handler):
        """'今天花了多少'."""
        result = send_message(
            live_minimax_handler, "今天花了多少钱",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(result)

    def test_plan_tomorrow(self, live_minimax_handler):
        """'明天要做的事：交报告'."""
        result = send_message(
            live_minimax_handler, "帮我记一下明天要交报告",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)


class TestBedtime:
    """Bedtime: exercise checkin, weekly stats."""

    def test_exercise_checkin(self, live_minimax_handler):
        """'跑了3公里'."""
        send_message(
            live_minimax_handler, "创建一个跑步打卡习惯",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler, "跑了3公里",
            session_key=SK,
            rubric=ConversationRubric(expect_tool_called="habit_checkin"),
        )
        assert_turn_passed(result)

    def test_weekly_habit_stats(self, live_minimax_handler):
        """'这周打卡情况怎么样'."""
        result = send_message(
            live_minimax_handler, "这周打卡情况怎么样",
            session_key=SK,
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_stats", "habit_list"],
            ),
        )
        assert_turn_passed(result)
