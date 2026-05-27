"""Conversational tests — intent disambiguation.

Tests that the LLM correctly routes ambiguous user intents to the
right tool, distinguishing memo vs memory, contact vs memo, expense
vs memo, habit vs memo, query vs create, delegate vs direct action.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_disambiguation.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestMemoryVsMemo:
    """Distinguish butler_remember (preferences) vs memo_add (tasks)."""

    def test_remember_task_uses_memo(self, live_minimax_handler):
        """'记一下明天开会' → memo_add, NOT butler_remember."""
        result = send_message(
            live_minimax_handler,
            "记一下明天开会",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_remember_preference_uses_memory(self, live_minimax_handler):
        """'记住我不吃辣' → butler_remember, NOT memo_add."""
        result = send_message(
            live_minimax_handler,
            "记住我不吃辣",
            rubric=ConversationRubric(expect_tool_called="butler_remember"),
        )
        assert_turn_passed(result)

    def test_remember_hobby_uses_memory(self, live_minimax_handler):
        """'记住我喜欢看科幻电影' → butler_remember."""
        result = send_message(
            live_minimax_handler,
            "记住我喜欢看科幻电影",
            rubric=ConversationRubric(expect_tool_called="butler_remember"),
        )
        assert_turn_passed(result)


class TestContactVsMemo:
    """Distinguish contact_add vs memo_add when '记一下' is used."""

    def test_phone_number_uses_contact(self, live_minimax_handler):
        """'记一下老张 13900001234' → contact_add."""
        result = send_message(
            live_minimax_handler,
            "记一下老张 13900001234",
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(result)


class TestExpenseVsMemo:
    """Distinguish expense_add vs memo_add when amounts are mentioned."""

    def test_amount_uses_expense(self, live_minimax_handler):
        """'晚上请客吃饭850' → expense_add."""
        result = send_message(
            live_minimax_handler,
            "晚上请客吃饭850",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)


class TestHabitVsMemo:
    """Distinguish habit_create vs memo_add for recurring activities."""

    def test_daily_activity_uses_habit(self, live_minimax_handler):
        """'以后每天喝水' → habit_create."""
        result = send_message(
            live_minimax_handler,
            "以后每天喝8杯水",
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        assert_turn_passed(result)

    def test_checkin_uses_habit(self, live_minimax_handler):
        """'今天的水喝完了' after creating habit → habit_checkin."""
        send_message(
            live_minimax_handler,
            "帮我创建一个每天喝水的习惯",
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler,
            "今天的水喝完了",
            rubric=ConversationRubric(expect_tool_called="habit_checkin"),
        )
        assert_turn_passed(result)


class TestQueryVsCreate:
    """Distinguish listing/searching vs creating."""

    def test_query_memo_uses_list(self, live_minimax_handler):
        """'我的备忘呢' → memo_list, NOT memo_add."""
        result = send_message(
            live_minimax_handler,
            "我的备忘呢",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
            ),
        )
        assert_turn_passed(result)

    def test_done_uses_update(self, live_minimax_handler):
        """'开会这个搞定了' → memo_update, NOT memo_delete."""
        send_message(
            live_minimax_handler,
            "帮我记一下明天开会",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        result = send_message(
            live_minimax_handler,
            "开会那个搞定了",
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_update", "memo_delete"],
            ),
        )
        assert_turn_passed(result)

    def test_habit_stats_uses_list(self, live_minimax_handler):
        """'查看我的打卡记录' → habit_list or habit_stats."""
        result = send_message(
            live_minimax_handler,
            "查看我的打卡记录",
            rubric=ConversationRubric(
                expect_any_tool_called=["habit_list", "habit_stats"],
            ),
        )
        assert_turn_passed(result)


class TestDelegateVsDirect:
    """Distinguish delegate_task vs direct tool use."""

    def test_read_code_direct(self, lingwen_handler):
        """'看一下项目代码' → read/list (direct), NOT delegate."""
        result = send_message(
            lingwen_handler,
            "看一下项目有什么文件",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory", "read_file"],
            ),
        )
        assert_turn_passed(result)

    def test_modify_code_delegates(self, lingwen_handler):
        """'改一下项目代码' → delegate_task (butler should not write directly)."""
        result = send_message(
            lingwen_handler,
            "帮我改一下项目的 README，加上一行版本号",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "read_file"],
            ),
        )
        assert_turn_passed(result)


class TestNoToolTrigger:
    """Inputs that should NOT trigger any tool."""

    def test_bare_number_no_tool(self, live_minimax_handler):
        """'35' alone should not trigger expense_add."""
        result = send_message(
            live_minimax_handler,
            "35",
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_bare_time_no_tool(self, live_minimax_handler):
        """'明天下午' alone — not enough info for any tool."""
        result = send_message(
            live_minimax_handler,
            "明天下午",
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)
