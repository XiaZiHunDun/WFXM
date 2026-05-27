"""Conversational tests — context reference / multi-turn coherence.

Tests that the LLM maintains context across turns and correctly
resolves pronouns, omissions, and references to prior results.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_context_ref.py -v
"""

from __future__ import annotations

import logging

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import (
    ConversationRubric,
    assert_turn_passed,
)

logger = logging.getLogger(__name__)


class TestMemoContextRef:
    """Context references in memo operations."""

    def test_modify_previous_memo(self, live_minimax_handler):
        """'记一下明天开会' → '改成后天'."""
        sk = "wechat:ctx-memo-modify"
        r1 = send_message(
            live_minimax_handler, "记一下明天开会",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "改成后天",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_update", "memo_add"],
            ),
        )
        assert_turn_passed(r2)

    def test_append_to_memo(self, live_minimax_handler):
        """'记一下周末买菜' → '对了还有买酱油'."""
        sk = "wechat:ctx-memo-append"
        send_message(
            live_minimax_handler, "记一下周末买菜",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        r2 = send_message(
            live_minimax_handler, "对了还有买酱油",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_add", "memo_update"],
            ),
        )
        assert_turn_passed(r2)

    def test_delete_last_memo(self, live_minimax_handler):
        """'删掉上一条备忘' — reference to the most recent memo."""
        sk = "wechat:ctx-memo-del"
        send_message(
            live_minimax_handler, "帮我记一下明天去邮局",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        r2 = send_message(
            live_minimax_handler, "删掉上一条备忘",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_delete", "memo_list"],
            ),
        )
        assert_turn_passed(r2)

    def test_two_part_memo(self, live_minimax_handler):
        """Fragment input: '帮我记个事' → '周六搬家'."""
        sk = "wechat:ctx-memo-frag"
        r1 = send_message(
            live_minimax_handler, "帮我记个事",
            session_key=sk,
        )
        r2 = send_message(
            live_minimax_handler, "周六搬家",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["搬家"],
            ),
        )
        assert_turn_passed(r2)


class TestContactContextRef:
    """Context references in contact operations."""

    def test_pronoun_he_contact(self, live_minimax_handler):
        """'存一下张三 139...' → '他的邮箱是 zhang@test.com'."""
        sk = "wechat:ctx-ct-he"
        send_message(
            live_minimax_handler, "存一下张三 13900001234",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        r2 = send_message(
            live_minimax_handler, "他的邮箱是 zhang@test.com",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_update", "contact_add"],
            ),
        )
        assert_turn_passed(r2)

    def test_same_person_query(self, live_minimax_handler):
        """'张三的电话' → '微信呢' (same person, different field)."""
        sk = "wechat:ctx-ct-same"
        send_message(
            live_minimax_handler, "张三的电话是多少",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_find"),
        )
        r2 = send_message(
            live_minimax_handler, "微信呢",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_find"],
            ),
        )
        assert_turn_passed(r2)

    def test_three_part_contact(self, live_minimax_handler):
        """Three-part info: name → company → phone."""
        sk = "wechat:ctx-ct-3part"
        send_message(
            live_minimax_handler, "存一下快递员电话",
            session_key=sk,
        )
        send_message(
            live_minimax_handler, "顺丰的",
            session_key=sk,
        )
        r3 = send_message(
            live_minimax_handler, "18012345678",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_add"],
            ),
        )
        assert_turn_passed(r3)


class TestExpenseContextRef:
    """Context references in expense operations."""

    def test_add_another_expense(self, live_minimax_handler):
        """'午饭花了35' → '再加一笔，打车20'."""
        sk = "wechat:ctx-exp-add"
        send_message(
            live_minimax_handler, "午饭花了35",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r2 = send_message(
            live_minimax_handler, "再加一笔，打车20",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r2)

    def test_total_from_context(self, live_minimax_handler):
        """Add two expenses, then ask total."""
        sk = "wechat:ctx-exp-total"
        send_message(
            live_minimax_handler, "午饭35",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        send_message(
            live_minimax_handler, "打车20",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r3 = send_message(
            live_minimax_handler, "一共多少",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(r3)

    def test_switch_category_same_period(self, live_minimax_handler):
        """'这个月花了多少' → '交通方面呢'."""
        sk = "wechat:ctx-exp-cat"
        send_message(
            live_minimax_handler, "这个月花了多少",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        r2 = send_message(
            live_minimax_handler, "交通方面呢",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(r2)

    def test_consecutive_expense_mode(self, live_minimax_handler):
        """Enter '记账' mode then rapid entries."""
        sk = "wechat:ctx-exp-mode"
        send_message(
            live_minimax_handler, "帮我记几笔账",
            session_key=sk,
        )
        r1 = send_message(
            live_minimax_handler, "午餐 25",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r1)
        r2 = send_message(
            live_minimax_handler, "晚餐 45",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r2)


class TestHabitContextRef:
    """Context references in habit operations."""

    def test_omit_habit_name_checkin(self, live_minimax_handler):
        """Create habit, then just say '打卡'."""
        sk = "wechat:ctx-habit-omit"
        send_message(
            live_minimax_handler, "创建一个每天跑步的习惯",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        r2 = send_message(
            live_minimax_handler, "打卡",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_checkin", "habit_list"],
            ),
        )
        assert_turn_passed(r2)


class TestDevContextRef:
    """Context references in dev scenarios."""

    def test_that_readme_ref(self, lingwen_handler):
        """'看看项目文件' → '那个 README 打开看看'."""
        sk = "wechat:ctx-dev-ref"
        send_message(
            lingwen_handler, "看看项目有哪些文件",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory"],
            ),
        )
        r2 = send_message(
            lingwen_handler, "那个 README 打开看看",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file"],
            ),
        )
        assert_turn_passed(r2)

    def test_cross_scene_flow(self, lingwen_handler):
        """Switch → read → delegate chain."""
        sk = "wechat:ctx-dev-flow"
        send_message(
            lingwen_handler, "切到灵文",
            session_key=sk,
        )
        send_message(
            lingwen_handler, "看看 README",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file", "list_directory"],
            ),
        )
        r3 = send_message(
            lingwen_handler, "帮我改一下标题",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "read_file"],
            ),
        )
        assert_turn_passed(r3)

    def test_list_then_filter(self, live_minimax_handler):
        """'帮我看看待办' → '标紧急的有哪些'."""
        sk = "wechat:ctx-filter"
        send_message(
            live_minimax_handler, "帮我看看有什么备忘",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
            ),
        )
        r2 = send_message(
            live_minimax_handler, "有没有标紧急的",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
            ),
        )
        assert_turn_passed(r2)

    def test_delegate_pronoun_he(self, lingwen_handler):
        """'委派给开发代理' → '让他检查代码'."""
        sk = "wechat:ctx-dev-he"
        send_message(
            lingwen_handler, "让开发代理看看项目",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "list_directory"],
            ),
        )
        r2 = send_message(
            lingwen_handler, "让他检查一下代码结构",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "list_directory", "read_file"],
            ),
        )
        assert_turn_passed(r2)
