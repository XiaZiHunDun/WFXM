"""Conversational tests — slash command routing.

Tests that gateway slash commands are correctly parsed and routed.
These tests use the handler directly and do NOT require LLM calls
for most sessionless commands (fast execution).

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_slash.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


# =========================================================================
# Daily slash commands (10)
# =========================================================================


class TestSlashDaily:
    """Daily-life slash commands."""

    def test_slash_memo_list(self, live_minimax_handler):
        """/备忘 → list memos."""
        result = send_message(
            live_minimax_handler, "/备忘",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_memo_add(self, live_minimax_handler):
        """/备忘 添加 明天开会."""
        result = send_message(
            live_minimax_handler, "/备忘 添加 明天开会",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_memo_search(self, live_minimax_handler):
        """/备忘 搜索 开会."""
        result = send_message(
            live_minimax_handler, "/备忘 搜索 开会",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_contacts_list(self, live_minimax_handler):
        """/通讯录 → list contacts."""
        result = send_message(
            live_minimax_handler, "/通讯录",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_contacts_add(self, live_minimax_handler):
        """/通讯录 添加 张三 13900001234."""
        result = send_message(
            live_minimax_handler, "/通讯录 添加 张三 13900001234",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_expense_summary(self, live_minimax_handler):
        """/记账 → monthly summary."""
        result = send_message(
            live_minimax_handler, "/记账",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_expense_add(self, live_minimax_handler):
        """/记账 记 午饭35."""
        result = send_message(
            live_minimax_handler, "/记账 记 午饭35",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_expense_weekly(self, live_minimax_handler):
        """/记账 本周."""
        result = send_message(
            live_minimax_handler, "/记账 本周",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_habits_list(self, live_minimax_handler):
        """/打卡 → list habits."""
        result = send_message(
            live_minimax_handler, "/打卡",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_habits_create(self, live_minimax_handler):
        """/打卡 创建 喝水 每天."""
        result = send_message(
            live_minimax_handler, "/打卡 创建 喝水 每天",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)


# =========================================================================
# Project slash commands (4)
# =========================================================================


class TestSlashProject:
    """Project management slash commands."""

    def test_slash_projects(self, lingwen_handler):
        """/项目 → list projects."""
        result = send_message(
            lingwen_handler, "/项目",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_slash_switch(self, lingwen_handler):
        """/切换 灵文1号."""
        result = send_message(
            lingwen_handler, "/切换 灵文1号",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_keywords=["已切换"],
            ),
        )
        assert_turn_passed(result)

    def test_slash_status(self, lingwen_handler):
        """/状态 → current status."""
        result = send_message(
            lingwen_handler, "/状态",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_slash_overview(self, lingwen_handler):
        """/总览 → all projects dashboard."""
        result = send_message(
            lingwen_handler, "/总览",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)


# =========================================================================
# Dev slash commands (6)
# =========================================================================


class TestSlashDev:
    """Development slash commands."""

    def test_slash_git_status(self, lingwen_handler):
        """/git → status."""
        result = send_message(
            lingwen_handler, "/git",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_git_diff(self, lingwen_handler):
        """/git diff."""
        result = send_message(
            lingwen_handler, "/git diff",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_git_log(self, lingwen_handler):
        """/git log 5."""
        result = send_message(
            lingwen_handler, "/git log 5",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_test(self, lingwen_handler):
        """/测试 → run tests."""
        result = send_message(
            lingwen_handler, "/测试",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_build(self, lingwen_handler):
        """/构建 → run build."""
        result = send_message(
            lingwen_handler, "/构建",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_dashboard(self, lingwen_handler):
        """/项目概况 → project dashboard."""
        result = send_message(
            lingwen_handler, "/项目概况",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)


# =========================================================================
# System slash commands (5)
# =========================================================================


class TestSlashSystem:
    """System-level slash commands."""

    def test_slash_new_session(self, live_minimax_handler):
        """/新对话 → reset session."""
        result = send_message(
            live_minimax_handler, "/新对话",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_help(self, live_minimax_handler):
        """/帮助 → help text."""
        result = send_message(
            live_minimax_handler, "/帮助",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_slash_model(self, live_minimax_handler):
        """/模型 → model info."""
        result = send_message(
            live_minimax_handler, "/模型",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_slash_todos(self, live_minimax_handler):
        """/待办 → todo list."""
        result = send_message(
            live_minimax_handler, "/待办",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert_turn_passed(result)

    def test_slash_health(self, live_minimax_handler):
        """/诊断 → health check."""
        result = send_message(
            live_minimax_handler, "/诊断",
            rubric=ConversationRubric(reject_keywords=["traceback"]),
        )
        assert result.response.strip()
        assert_turn_passed(result)
