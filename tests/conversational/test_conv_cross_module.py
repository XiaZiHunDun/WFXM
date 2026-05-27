"""Conversational tests — cross-module interaction.

Tests scenarios where a single user message or a short conversation
touches multiple tool modules (e.g., expense + memo, contact + memo,
habit + expense).

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_cross_module.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestExpensePlusMemo:
    """Combined expense tracking and memo creation."""

    def test_doctor_visit(self, live_minimax_handler):
        """'今天看病花了300，下次复查是下周五'."""
        sk = "wechat:cross-doc"
        result = send_message(
            live_minimax_handler,
            "今天看病花了300，帮我记一下下次复查是下周五",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_shopping_then_list(self, live_minimax_handler):
        """'超市买了牛奶面包一共45' → '加到购物清单明天再买水果'."""
        sk = "wechat:cross-shop"
        send_message(
            live_minimax_handler,
            "超市买了牛奶面包一共45",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r2 = send_message(
            live_minimax_handler,
            "帮我记一下明天还要买点水果",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(r2)


class TestMemoPlusContact:
    """Combined memo and contact operations."""

    def test_appointment_with_contact(self, live_minimax_handler):
        """'帮我约张三周六吃饭' → memo + possibly query contact."""
        result = send_message(
            live_minimax_handler,
            "帮我记一下周六约张三吃饭",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add"],
            ),
        )
        assert_turn_passed(result)

    def test_trip_plus_contact(self, live_minimax_handler):
        """'帮我记一下下周出差，联系一下李秘书'."""
        result = send_message(
            live_minimax_handler,
            "帮我记一下下周出差，另外帮我查一下李秘书的电话",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add", "contact_find"],
            ),
        )
        assert_turn_passed(result)


class TestHabitPlusExpense:
    """Combined habit creation and expense tracking."""

    def test_gym_membership(self, live_minimax_handler):
        """'健身卡花了2000，帮我创建每天健身的习惯'."""
        result = send_message(
            live_minimax_handler,
            "健身卡花了2000，帮我创建一个每天健身的习惯",
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "habit_create"],
            ),
        )
        assert_turn_passed(result)


class TestMemoryPlusMemo:
    """Combined memory and memo operations."""

    def test_remember_then_book(self, live_minimax_handler):
        """'记住我喜欢去XX餐厅，帮我约个这周五去'."""
        result = send_message(
            live_minimax_handler,
            "记住我喜欢去小龙虾馆，帮我约个这周五去吃",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember", "memo_add"],
            ),
        )
        assert_turn_passed(result)


class TestMultiExpense:
    """Multiple expenses in rapid sequence then summary."""

    def test_triple_expense_then_total(self, live_minimax_handler):
        """'午饭25晚饭45打车30' → '今天一共花了多少'."""
        sk = "wechat:cross-exp-total"
        send_message(
            live_minimax_handler, "午饭25",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        send_message(
            live_minimax_handler, "晚饭45",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        send_message(
            live_minimax_handler, "打车30",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r4 = send_message(
            live_minimax_handler, "今天一共花了多少",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(r4)


class TestMultiMemo:
    """Multiple memos for planning."""

    def test_plan_tomorrow(self, live_minimax_handler):
        """'明天要做的事：交报告、约牙医、买菜'."""
        result = send_message(
            live_minimax_handler,
            "帮我安排一下明天的事：交报告、约牙医、去超市买菜",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add"],
            ),
        )
        assert_turn_passed(result)


class TestMemoPlusReminder:
    """Combined memo and reminder."""

    def test_memo_with_reminder(self, live_minimax_handler):
        """'明天下午3点开会，到时候提醒我一下'."""
        result = send_message(
            live_minimax_handler,
            "明天下午3点开会，到时候提醒我一下",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add", "set_reminder"],
            ),
        )
        assert_turn_passed(result)


class TestContactPlusDelegate:
    """Contact query then delegation."""

    def test_find_then_delegate(self, lingwen_handler):
        """Query contact, then delegate."""
        sk = "wechat:cross-ct-del"
        send_message(
            lingwen_handler,
            "查一下项目组张三的联系方式",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_find"],
            ),
        )
        r2 = send_message(
            lingwen_handler,
            "让开发代理整理一下项目文档",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "list_directory"],
            ),
        )
        assert_turn_passed(r2)
