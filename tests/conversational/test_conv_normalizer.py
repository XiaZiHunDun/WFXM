"""Conversational tests — gateway normalizer verification.

Tests that natural language inputs are correctly normalized to their
corresponding slash commands by the gateway normalizer chain in
message_handler.py before hitting the LLM loop.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_normalizer.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestSwitchNormalizer:
    """Natural language → /切换."""

    def test_switch_standard(self, lingwen_handler):
        """'切换到灵文1号' → /切换 灵文1号."""
        result = send_message(
            lingwen_handler, "切换到灵文1号",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(expect_keywords=["已切换"]),
        )
        assert_turn_passed(result)

    def test_switch_short(self, lingwen_handler):
        """'切到灵文' → /切换 灵文."""
        result = send_message(
            lingwen_handler, "切到灵文",
            session_key="wechat:conv-dev",
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_switch_back(self, lingwen_handler):
        """'切回灵文1号'."""
        result = send_message(
            lingwen_handler, "切回灵文1号",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(expect_keywords=["已切换"]),
        )
        assert_turn_passed(result)


class TestStatusNormalizer:
    """Natural language → /状态 or /项目."""

    def test_which_project(self, lingwen_handler):
        """'当前在哪个项目' → /状态."""
        result = send_message(
            lingwen_handler, "当前在哪个项目",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_list_projects(self, lingwen_handler):
        """'有哪些项目' → /项目."""
        result = send_message(
            lingwen_handler, "有哪些项目",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_overview(self, lingwen_handler):
        """'看看所有项目状态' → /总览."""
        result = send_message(
            lingwen_handler, "看看所有项目状态",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)


class TestDailyNormalizer:
    """Natural language → daily slash commands."""

    def test_check_memo(self, live_minimax_handler):
        """'查看备忘' → /备忘."""
        result = send_message(
            live_minimax_handler, "查看备忘",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_my_memos(self, live_minimax_handler):
        """'我的备忘录' → /备忘."""
        result = send_message(
            live_minimax_handler, "我的备忘录",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_checkin(self, live_minimax_handler):
        """'打卡' → /打卡."""
        result = send_message(
            live_minimax_handler, "打卡",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_today_checkin(self, live_minimax_handler):
        """'今日打卡' → /打卡."""
        result = send_message(
            live_minimax_handler, "今日打卡",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_my_contacts(self, live_minimax_handler):
        """'我的通讯录' → /通讯录."""
        result = send_message(
            live_minimax_handler, "我的通讯录",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_monthly_expense(self, live_minimax_handler):
        """'本月支出' → /记账."""
        result = send_message(
            live_minimax_handler, "本月支出",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_my_bills(self, live_minimax_handler):
        """'我的账单' → /记账."""
        result = send_message(
            live_minimax_handler, "我的账单",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)


class TestDetailNormalizer:
    """Natural language → /详细."""

    def test_detail_request(self, live_minimax_handler):
        """'详细看看' → /详细."""
        result = send_message(
            live_minimax_handler, "详细看看",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)
