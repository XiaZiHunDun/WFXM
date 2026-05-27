"""Conversational tests — rapid-fire / consecutive message patterns.

Tests that the butler handles rapid sequences of messages correctly,
including consecutive same-type operations, mixed-type rapid input,
fragment assembly, and correction sequences.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_rapid_fire.py -v
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


class TestConsecutiveExpenses:
    """Rapid consecutive expense entries."""

    def test_three_meals(self, live_minimax_handler):
        """Three meals in quick succession + total."""
        sk = "wechat:rapid-exp"
        r1 = send_message(
            live_minimax_handler, "早餐12",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "午饭35",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r2)
        r3 = send_message(
            live_minimax_handler, "晚饭48",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r3)
        r4 = send_message(
            live_minimax_handler, "今天一共多少",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(r4)


class TestConsecutiveContacts:
    """Rapid consecutive contact saves."""

    def test_three_contacts(self, live_minimax_handler):
        """Three contacts in a row."""
        sk = "wechat:rapid-ct"
        r1 = send_message(
            live_minimax_handler, "存一下张三 13900001111",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "李四 13800002222",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(r2)
        r3 = send_message(
            live_minimax_handler, "王五 13700003333",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(r3)


class TestConsecutiveMemos:
    """Rapid consecutive memo creation."""

    def test_three_tasks(self, live_minimax_handler):
        """Three tasks rapid fire."""
        sk = "wechat:rapid-memo"
        r1 = send_message(
            live_minimax_handler, "明天交报告",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "周三面试",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(r2)
        r3 = send_message(
            live_minimax_handler, "周五体检",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(r3)


class TestRapidHabitCheckin:
    """Rapid habit check-ins."""

    def test_quick_checkins(self, live_minimax_handler):
        """Three habits checked in rapidly."""
        sk = "wechat:rapid-habit"
        send_message(
            live_minimax_handler, "创建喝水习惯",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        send_message(
            live_minimax_handler, "创建跑步习惯",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        r1 = send_message(
            live_minimax_handler, "喝水打卡",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="habit_checkin"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "跑步也打卡",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="habit_checkin"),
        )
        assert_turn_passed(r2)


class TestMixedRapidFire:
    """Mixed-type rapid fire messages."""

    def test_expense_contact_memo_mix(self, live_minimax_handler):
        """Three different types in quick succession."""
        sk = "wechat:rapid-mix"
        r1 = send_message(
            live_minimax_handler, "午饭30",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "存一下外卖小哥 18600001234",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(r2)
        r3 = send_message(
            live_minimax_handler, "下班记得5点半走",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(r3)


class TestCorrectionSequence:
    """Quick correction in rapid sequence."""

    def test_amount_correction(self, live_minimax_handler):
        """'花了35' → '不对不对' → '是45'."""
        sk = "wechat:rapid-corr"
        send_message(
            live_minimax_handler, "午饭花了35",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        send_message(
            live_minimax_handler, "不对不对",
            session_key=sk,
        )
        r3 = send_message(
            live_minimax_handler, "是45",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "expense_delete"],
            ),
        )
        assert_turn_passed(r3)


class TestMultiIntentSingle:
    """Multiple intents in a single message."""

    def test_three_tasks_one_message(self, live_minimax_handler):
        """'帮我办三件事：记账午饭30、存张三电话、明天开会'."""
        result = send_message(
            live_minimax_handler,
            "帮我办三件事：记账午饭30块、存一下张三电话13900001234、明天下午开会帮我记着",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "contact_add", "memo_add"],
            ),
        )
        assert_turn_passed(result)


class TestSequentialQuery:
    """Rapid query sequence."""

    def test_project_info_flow(self, lingwen_handler):
        """'几个项目' → '第一个什么状态' → '切过去看看'."""
        sk = "wechat:rapid-proj"
        r1 = send_message(
            lingwen_handler, "有几个项目",
            session_key=sk,
        )
        assert r1.response.strip()
        r2 = send_message(
            lingwen_handler, "灵文是什么状态",
            session_key=sk,
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert r2.response.strip()
        assert_turn_passed(r2)


class TestNonTriggering:
    """Messages that should NOT trigger tools during rapid fire."""

    def test_urge_no_tool(self, live_minimax_handler):
        """'快点' and '好了吗' should not trigger tools."""
        sk = "wechat:rapid-noop"
        r1 = send_message(
            live_minimax_handler, "快点",
            session_key=sk,
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert r1.response.strip()
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "好了吗",
            session_key=sk,
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert r2.response.strip()
        assert_turn_passed(r2)
