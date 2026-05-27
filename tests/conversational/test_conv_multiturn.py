"""Conversational tests — multi-turn dialogue scenarios.

Tests context retention and task coherence across multiple turns:
  - Daily multi-turn (6 cases):
      - memo CRUD lifecycle
      - contact add+find
      - expense add+summary
      - expense flow (add+query+delete)
      - contacts flow (add+update+query)
      - mixed scenario (expense+memo)
  - Dev multi-turn (4 cases):
      - switch+delegate+status
      - read+delegate
      - delegate+status+detail
      - project switch+read+memory

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_multiturn.py -v --timeout=180
"""

from __future__ import annotations

import logging

import pytest

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import (
    ConversationRubric,
    TurnResult,
    assert_turn_passed,
    evaluate_turn,
    format_report,
)

logger = logging.getLogger(__name__)


# =========================================================================
# Daily multi-turn (6)
# =========================================================================


class TestMemoMultiTurnConversational:
    """Multi-turn memo lifecycle: add → query → delete → verify."""

    def test_memo_lifecycle(self, live_minimax_handler):
        """Full memo CRUD in 4 conversational turns."""
        sk = "wechat:conv-multiturn-memo"
        results: list[TurnResult] = []

        r1 = send_message(
            live_minimax_handler,
            "帮我记一下后天上午去银行办事",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["银行"],
            ),
        )
        assert_turn_passed(r1)
        results.append(r1)

        r2 = send_message(
            live_minimax_handler,
            "我有哪些备忘事项",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
                soft_keywords=["银行"],
            ),
        )
        assert_turn_passed(r2)
        results.append(r2)

        r3 = send_message(
            live_minimax_handler,
            "把去银行那个备忘删掉",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_delete", "memo_update"],
            ),
        )
        assert_turn_passed(r3)
        results.append(r3)

        r4 = send_message(
            live_minimax_handler,
            "现在还有什么备忘吗",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_list", "memo_search"],
            ),
        )
        assert_turn_passed(r4)
        results.append(r4)

        report = format_report(results)
        logger.info("\n%s", report)


class TestContactExpenseMultiTurnConversational:
    """Multi-turn: add contact then query, add expense then summarize."""

    def test_contact_add_then_find(self, live_minimax_handler):
        """Add a contact, then look them up."""
        sk = "wechat:conv-multiturn-contact"

        r1 = send_message(
            live_minimax_handler,
            "帮我存一下赵会计的电话 18600001111",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="contact_add",
            ),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            live_minimax_handler,
            "赵会计的联系方式是什么",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="contact_find",
                soft_keywords=["赵会计", "186"],
            ),
        )
        assert_turn_passed(r2)

    def test_expense_add_then_summary(self, live_minimax_handler):
        """Log expenses, then ask for a monthly summary."""
        sk = "wechat:conv-multiturn-expense"

        r1 = send_message(
            live_minimax_handler,
            "今天打车花了28块",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="expense_add",
            ),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            live_minimax_handler,
            "这个月的支出情况怎么样",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_summary", "expense_list"],
            ),
        )
        assert_turn_passed(r2)


class TestExpenseFlowMultiTurn:
    """Multi-turn expense flow: add → query → delete."""

    def test_expense_add_query_delete(self, live_minimax_handler):
        """Add expense, query, then delete."""
        sk = "wechat:conv-multiturn-expflow"

        r1 = send_message(
            live_minimax_handler,
            "买书花了120块",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            live_minimax_handler,
            "看看今天有哪些支出",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_list", "expense_summary"],
            ),
        )
        assert_turn_passed(r2)

        r3 = send_message(
            live_minimax_handler,
            "买书那笔记错了，帮我删掉",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_delete", "expense_list"],
            ),
        )
        assert_turn_passed(r3)


class TestContactFlowMultiTurn:
    """Multi-turn contacts flow: add → update → query."""

    def test_contact_add_update_query(self, live_minimax_handler):
        """Add, update, then query a contact."""
        sk = "wechat:conv-multiturn-ctflow"

        r1 = send_message(
            live_minimax_handler,
            "存一下孙总的电话 15000001234",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            live_minimax_handler,
            "孙总的邮箱是 sun@corp.com，也帮我存一下",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_add", "contact_update"],
            ),
        )
        assert_turn_passed(r2)

        r3 = send_message(
            live_minimax_handler,
            "孙总的所有联系方式是什么",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="contact_find",
                soft_keywords=["孙总"],
            ),
        )
        assert_turn_passed(r3)


class TestMixedScenarioMultiTurn:
    """Multi-turn mixed: expense + memo in one flow."""

    def test_expense_then_memo(self, live_minimax_handler):
        """Record expense then add a related memo."""
        sk = "wechat:conv-multiturn-mixed"

        r1 = send_message(
            live_minimax_handler,
            "刚交了3000块房租",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            live_minimax_handler,
            "提醒我下个月1号之前也要交房租",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="memo_add",
                soft_keywords=["房租"],
            ),
        )
        assert_turn_passed(r2)


# =========================================================================
# Dev multi-turn (4)
# =========================================================================


class TestDevMultiTurnConversational:
    """Multi-turn dev scenario: switch project → delegate → check status."""

    def test_switch_then_delegate(self, lingwen_handler):
        """Switch to LingWen1, delegate a content task, check result."""
        sk = "wechat:conv-dev"
        results: list[TurnResult] = []

        r1 = send_message(
            lingwen_handler,
            "切换到灵文1号",
            session_key=sk,
            rubric=ConversationRubric(
                expect_keywords=["已切换"],
            ),
        )
        assert_turn_passed(r1)
        results.append(r1)

        r2 = send_message(
            lingwen_handler,
            "让内容代理在 docs 目录创建一个 multi-turn-test.md 文件，写一行 MULTITURN_OK",
            session_key=sk,
            rubric=ConversationRubric(
                expect_tool_called="delegate_task",
            ),
        )
        assert_turn_passed(r2)
        results.append(r2)

        r3 = send_message(
            lingwen_handler,
            "刚才委派的任务完成了吗",
            session_key=sk,
            rubric=ConversationRubric(
                reject_keywords=["error", "异常"],
            ),
        )
        assert r3.response.strip(), "Should produce a status response"
        assert_turn_passed(r3)
        results.append(r3)

        report = format_report(results)
        logger.info("\n%s", report)

    def test_read_then_delegate(self, lingwen_handler):
        """Read README first, then delegate based on what's found."""
        sk = "wechat:conv-dev"

        r1 = send_message(
            lingwen_handler,
            "先看看项目的 README 文件",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file", "list_directory"],
            ),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            lingwen_handler,
            "帮我交给开发代理，分析一下这个项目的目录结构",
            session_key=sk,
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        assert len(r2.tool_events) > 0 or r2.response.strip(), (
            "Expected either tool calls or a response"
        )
        assert_turn_passed(r2)


class TestDevDelegateStatusMultiTurn:
    """Multi-turn: delegate → check status → get details."""

    def test_delegate_then_status_then_detail(self, lingwen_handler):
        """Delegate, ask status, then ask for details."""
        sk = "wechat:conv-dev-status"

        r1 = send_message(
            lingwen_handler,
            "让开发代理列一下项目所有的文件",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "delegate_task", "list_directory",
                ],
            ),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            lingwen_handler,
            "完成了吗？结果怎么样",
            session_key=sk,
            rubric=ConversationRubric(
                reject_keywords=["error", "异常"],
            ),
        )
        assert r2.response.strip()
        assert_turn_passed(r2)

        r3 = send_message(
            lingwen_handler,
            "能给我看看 docs 目录下有什么",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory", "read_file"],
            ),
        )
        assert_turn_passed(r3)


class TestDevProjectSwitchAndMemoryMultiTurn:
    """Multi-turn: switch project → read → remember something."""

    def test_switch_read_remember(self, lingwen_handler):
        """Switch, read, then remember a note about the project."""
        sk = "wechat:conv-dev-memo"

        r1 = send_message(
            lingwen_handler,
            "切换到灵文1号",
            session_key=sk,
            rubric=ConversationRubric(
                expect_keywords=["已切换"],
            ),
        )
        assert_turn_passed(r1)

        r2 = send_message(
            lingwen_handler,
            "看一下 README.md",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file"],
            ),
        )
        assert_turn_passed(r2)

        r3 = send_message(
            lingwen_handler,
            "记住这个项目是小说工厂试点",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember"],
            ),
        )
        assert_turn_passed(r3)
