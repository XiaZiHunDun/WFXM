"""Conversational tests — daily life scenarios.

Single-turn tests with real MiniMax LLM covering:
  - Memo management (10 cases)
  - Contacts management (7 cases)
  - Expense tracking (7 cases)
  - Habit tracking (6 cases)
  - General conversation (5 cases)

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_daily.py -v --timeout=120
"""

from __future__ import annotations

import pytest

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import (
    ConversationRubric,
    assert_turn_passed,
    format_report,
)


# =========================================================================
# Memo scenarios (10)
# =========================================================================


class TestMemoConversational:
    """Natural language memo management."""

    def test_memo_add_meeting(self, live_minimax_handler):
        """Natural request to remember a meeting tomorrow."""
        result = send_message(
            live_minimax_handler,
            "帮我记一下明天下午3点开会",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                expect_tool_args_contain={"content": "开会"},
                soft_keywords=["已记录", "备忘"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_add_deadline(self, live_minimax_handler):
        """Reminder with a deadline."""
        result = send_message(
            live_minimax_handler,
            "提醒我周五之前交报告给老板",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["报告"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_add_health(self, live_minimax_handler):
        """Health appointment — expect health category."""
        result = send_message(
            live_minimax_handler,
            "下周二牙医预约，上午10点",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["牙医"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_query_natural(self, live_minimax_handler):
        """Ask to see memos in natural language (may hit normalizer or Loop)."""
        result = send_message(
            live_minimax_handler,
            "帮我查一下最近有什么备忘",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_add_shopping(self, live_minimax_handler):
        """Simple shopping reminder."""
        result = send_message(
            live_minimax_handler,
            "记一下，明天要去超市买牛奶和面包",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["牛奶"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_modify(self, live_minimax_handler):
        """Add a memo then ask to modify it."""
        send_message(
            live_minimax_handler,
            "帮我记一下周六聚餐",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        result = send_message(
            live_minimax_handler,
            "把周六聚餐改成周日",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_update", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_add_with_priority(self, live_minimax_handler):
        """Add urgent memo — should pass priority field."""
        result = send_message(
            live_minimax_handler,
            "记一个紧急事项：明天交税截止",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["交税"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_cancel_reminder(self, live_minimax_handler):
        """Ask to cancel/delete a reminder."""
        send_message(
            live_minimax_handler,
            "帮我记一下后天取快递",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        result = send_message(
            live_minimax_handler,
            "取消取快递的提醒",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_delete", "memo_update"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_search_specific(self, live_minimax_handler):
        """Search for a specific memo by keyword."""
        send_message(
            live_minimax_handler,
            "帮我记一下下周一面试",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        result = send_message(
            live_minimax_handler,
            "帮我找一下关于面试的备忘",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_search", "memo_list"],
                soft_keywords=["面试"],
            ),
        )
        assert_turn_passed(result)

    def test_memo_complex_time_expr(self, live_minimax_handler):
        """Memo with complex time expression."""
        result = send_message(
            live_minimax_handler,
            "下个月第一个周末帮我安排一次家庭聚会",
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["聚会"],
            ),
        )
        assert_turn_passed(result)


# =========================================================================
# Contacts scenarios (7)
# =========================================================================


class TestContactsConversational:
    """Natural language contacts management."""

    def test_contact_add_phone(self, live_minimax_handler):
        """Save a doctor's phone number."""
        result = send_message(
            live_minimax_handler,
            "帮我存一下李医生的电话 13912345678",
            rubric=ConversationRubric(
                expect_tool_called="contact_add",
                soft_keywords=["李医生"],
            ),
        )
        assert_turn_passed(result)

    def test_contact_add_email(self, live_minimax_handler):
        """Save an email address."""
        result = send_message(
            live_minimax_handler,
            "王经理的邮箱是 wang@example.com，帮我记下来",
            rubric=ConversationRubric(
                expect_tool_called="contact_add",
                soft_keywords=["王经理"],
            ),
        )
        assert_turn_passed(result)

    def test_contact_query(self, live_minimax_handler):
        """Query for a contact's info."""
        result = send_message(
            live_minimax_handler,
            "张三的电话号码是多少",
            rubric=ConversationRubric(
                expect_tool_called="contact_find",
            ),
        )
        assert_turn_passed(result)

    def test_contact_update(self, live_minimax_handler):
        """Update an existing contact's info."""
        send_message(
            live_minimax_handler,
            "存一下刘总的电话 13800001111",
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        result = send_message(
            live_minimax_handler,
            "刘总换号了，新号码是 13900002222",
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_update", "contact_add"],
            ),
        )
        assert_turn_passed(result)

    def test_contact_delete(self, live_minimax_handler):
        """Delete a contact."""
        send_message(
            live_minimax_handler,
            "存一下测试联系人电话 10000000000",
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        result = send_message(
            live_minimax_handler,
            "把测试联系人删掉",
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_delete", "contact_find"],
            ),
        )
        assert_turn_passed(result)

    def test_contact_list_all(self, live_minimax_handler):
        """View all contacts."""
        result = send_message(
            live_minimax_handler,
            "看看我的通讯录里有谁",
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_find", "contact_list"],
            ),
        )
        assert_turn_passed(result)

    def test_contact_add_multiple_info(self, live_minimax_handler):
        """Add contact with both phone and email."""
        result = send_message(
            live_minimax_handler,
            "存一下陈律师的联系方式，电话 13700009999，邮箱 chen@lawfirm.com",
            rubric=ConversationRubric(
                expect_tool_called="contact_add",
                soft_keywords=["陈律师"],
            ),
        )
        assert_turn_passed(result)


# =========================================================================
# Expense scenarios (7)
# =========================================================================


class TestExpenseConversational:
    """Natural language expense tracking."""

    def test_expense_add_food(self, live_minimax_handler):
        """Log a lunch expense."""
        result = send_message(
            live_minimax_handler,
            "中午吃饭花了35块",
            rubric=ConversationRubric(
                expect_tool_called="expense_add",
            ),
        )
        assert_turn_passed(result)

    def test_expense_add_gas(self, live_minimax_handler):
        """Log a gas expense."""
        result = send_message(
            live_minimax_handler,
            "给车加油花了400",
            rubric=ConversationRubric(
                expect_tool_called="expense_add",
            ),
        )
        assert_turn_passed(result)

    def test_expense_query_monthly(self, live_minimax_handler):
        """Ask about monthly spending."""
        result = send_message(
            live_minimax_handler,
            "这个月一共花了多少钱",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(result)

    def test_expense_delete(self, live_minimax_handler):
        """Delete an expense record."""
        send_message(
            live_minimax_handler,
            "买水果花了50块",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        result = send_message(
            live_minimax_handler,
            "把买水果那笔删掉，记错了",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_delete", "expense_list"],
            ),
        )
        assert_turn_passed(result)

    def test_expense_query_by_category(self, live_minimax_handler):
        """Query expenses by category."""
        result = send_message(
            live_minimax_handler,
            "这个月交通方面花了多少",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(result)

    def test_expense_consecutive(self, live_minimax_handler):
        """Log multiple expenses in quick succession."""
        r1 = send_message(
            live_minimax_handler,
            "早餐花了15块",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler,
            "地铁卡充值50",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r2)

    def test_expense_income(self, live_minimax_handler):
        """Record income (positive flow)."""
        result = send_message(
            live_minimax_handler,
            "今天收到报销款2000块",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "expense_income"],
            ),
        )
        assert_turn_passed(result)


# =========================================================================
# Habits scenarios (6)
# =========================================================================


class TestHabitsConversational:
    """Natural language habit tracking."""

    def test_habit_create(self, live_minimax_handler):
        """Create a daily habit."""
        result = send_message(
            live_minimax_handler,
            "帮我创建一个每天喝8杯水的习惯",
            rubric=ConversationRubric(
                expect_tool_called="habit_create",
                soft_keywords=["喝水"],
            ),
        )
        assert_turn_passed(result)

    def test_habit_checkin(self, live_minimax_handler):
        """Check in for exercise — first create, then checkin."""
        send_message(
            live_minimax_handler,
            "帮我创建一个每天跑步的习惯",
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler,
            "我今天跑了5公里",
            rubric=ConversationRubric(
                expect_tool_called="habit_checkin",
            ),
        )
        assert_turn_passed(result)

    def test_habit_query(self, live_minimax_handler):
        """Ask about habit status."""
        result = send_message(
            live_minimax_handler,
            "我今天还有哪些习惯没打卡",
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_list", "habit_stats"],
            ),
        )
        assert_turn_passed(result)

    def test_habit_delete(self, live_minimax_handler):
        """Delete a habit."""
        send_message(
            live_minimax_handler,
            "帮我创建一个每天早起的习惯",
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler,
            "把早起的习惯删掉，我坚持不了",
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_delete", "habit_list"],
            ),
        )
        assert_turn_passed(result)

    def test_habit_stats(self, live_minimax_handler):
        """Ask for detailed habit statistics."""
        result = send_message(
            live_minimax_handler,
            "我这周的打卡情况怎么样，给我看看统计",
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_stats", "habit_list"],
            ),
        )
        assert_turn_passed(result)

    def test_habit_modify_frequency(self, live_minimax_handler):
        """Modify habit frequency."""
        send_message(
            live_minimax_handler,
            "帮我创建一个每天做俯卧撑的习惯",
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler,
            "把俯卧撑改成每周三次就行",
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_update", "habit_create"],
            ),
        )
        assert_turn_passed(result)


# =========================================================================
# General conversation scenarios (5)
# =========================================================================


class TestGeneralConversational:
    """General chat without specific tool calls."""

    def test_greeting(self, live_minimax_handler):
        """Simple greeting — should respond naturally, no tools."""
        result = send_message(
            live_minimax_handler,
            "你好",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "错误", "异常"],
            ),
        )
        assert result.response.strip(), "Greeting should produce a response"
        assert_turn_passed(result)

    def test_capability_inquiry(self, live_minimax_handler):
        """Ask what the butler can do."""
        result = send_message(
            live_minimax_handler,
            "你能帮我做什么",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "异常"],
            ),
        )
        assert result.response.strip(), "Capability inquiry should produce a response"
        assert_turn_passed(result)

    def test_weather_inquiry(self, live_minimax_handler):
        """Weather question — no tools available, should respond conversationally."""
        result = send_message(
            live_minimax_handler,
            "今天天气怎么样",
            rubric=ConversationRubric(
                reject_keywords=["error", "异常"],
            ),
        )
        assert result.response.strip(), "Weather inquiry should produce a response"
        assert_turn_passed(result)

    def test_gratitude_response(self, live_minimax_handler):
        """Thank you — should respond politely."""
        result = send_message(
            live_minimax_handler,
            "谢谢你帮了大忙",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "异常"],
            ),
        )
        assert result.response.strip(), "Gratitude should produce a response"
        assert_turn_passed(result)

    def test_complex_instruction_recognition(self, live_minimax_handler):
        """Complex instruction mixing memo and preference — LLM should disambiguate."""
        result = send_message(
            live_minimax_handler,
            "帮我记一下明天下午两点在星巴克见客户，还有记住我喜欢点冰美式",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add", "butler_remember"],
            ),
        )
        assert_turn_passed(result)
