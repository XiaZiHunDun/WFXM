"""Conversational tests — development scenarios (LingWen1 pilot).

Single-turn tests with real MiniMax LLM covering:
  - Project switching (4 cases)
  - Natural-language dev queries (6 cases)
  - Task delegation in Lead mode (6 cases)

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_dev.py -v --timeout=120
"""

from __future__ import annotations

import pytest

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import (
    ConversationRubric,
    assert_turn_passed,
)


# =========================================================================
# Project switching (4)
# =========================================================================


class TestProjectSwitchConversational:
    """Natural language project switching."""

    def test_switch_exact_name(self, lingwen_handler):
        """Switch with exact project name — should hit normalizer directly."""
        result = send_message(
            lingwen_handler,
            "切换到灵文1号",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_keywords=["已切换", "灵文"],
            ),
        )
        assert_turn_passed(result)

    def test_switch_variant(self, lingwen_handler):
        """Switch with a common variant — 'cut back to' pattern."""
        result = send_message(
            lingwen_handler,
            "切回灵文1号",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_keywords=["已切换"],
            ),
        )
        assert_turn_passed(result)

    def test_switch_invalid_project(self, lingwen_handler):
        """Switch to a non-existent project — should get error or clarification."""
        result = send_message(
            lingwen_handler,
            "切换到不存在的项目ABC",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                reject_keywords=["已切换"],
            ),
        )
        assert result.response.strip(), "Should give feedback about missing project"
        assert_turn_passed(result)

    def test_switch_fuzzy_name(self, lingwen_handler):
        """Switch with a fuzzy name variant."""
        result = send_message(
            lingwen_handler,
            "去灵文项目看看",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                reject_keywords=["error", "异常"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)


# =========================================================================
# Natural language dev queries (6)
# =========================================================================


class TestDevNaturalLanguageConversational:
    """Natural language dev queries that should go through Loop."""

    def test_ask_code_changes(self, lingwen_handler):
        """Ask about code changes — LLM should use git or read tools."""
        result = send_message(
            lingwen_handler,
            "看看项目有什么文件",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory", "read_file", "search_files"],
                reject_keywords=["error", "异常"],
            ),
        )
        assert_turn_passed(result)

    def test_ask_project_overview(self, lingwen_handler):
        """Ask about the project — LLM should gather info."""
        result = send_message(
            lingwen_handler,
            "灵文项目现在是什么情况",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                reject_keywords=["error", "异常"],
            ),
        )
        assert result.response.strip(), "Should produce a project overview"
        assert_turn_passed(result)

    def test_read_project_readme(self, lingwen_handler):
        """Ask to read the README — should use read_file."""
        result = send_message(
            lingwen_handler,
            "帮我看一下项目的 README 内容",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file", "list_directory"],
                soft_keywords=["灵文", "CONV_TEST_MARKER"],
            ),
        )
        assert_turn_passed(result)

    def test_search_code(self, lingwen_handler):
        """Search for specific code pattern."""
        result = send_message(
            lingwen_handler,
            "搜索一下项目里有没有 CONV_TEST_MARKER 这个关键词",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["search_files", "read_file"],
                soft_keywords=["CONV_TEST_MARKER"],
            ),
        )
        assert_turn_passed(result)

    def test_view_specific_file(self, lingwen_handler):
        """Ask to view a specific file."""
        result = send_message(
            lingwen_handler,
            "打开 README.md 看看写了什么",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file", "list_directory"],
            ),
        )
        assert_turn_passed(result)

    def test_query_project_structure(self, lingwen_handler):
        """Ask about project directory structure."""
        result = send_message(
            lingwen_handler,
            "项目的目录结构是怎样的",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory"],
                reject_keywords=["error", "异常"],
            ),
        )
        assert_turn_passed(result)


# =========================================================================
# Task delegation (6)
# =========================================================================


class TestDelegateConversational:
    """Task delegation in Lead mode — LLM should use delegate_task."""

    def test_delegate_content_task(self, lingwen_handler):
        """Ask to write content — should delegate to content agent."""
        result = send_message(
            lingwen_handler,
            "帮灵文项目在 docs 目录下写一个测试文件 conv-test.md，内容就写 hello",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_tool_called="delegate_task",
            ),
        )
        assert_turn_passed(result)

    def test_delegate_dev_task(self, lingwen_handler):
        """Ask dev agent to check code — delegate_task audit may be merged
        with sub-agent tool calls, so check for delegation evidence."""
        result = send_message(
            lingwen_handler,
            "让开发代理检查一下项目的代码结构",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "delegate_task", "list_directory", "read_file",
                ],
            ),
        )
        assert_turn_passed(result)

    def test_delegate_review_task(self, lingwen_handler):
        """Ask review agent to analyze progress — similar audit merging."""
        result = send_message(
            lingwen_handler,
            "找审阅代理分析一下项目当前的进展情况",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "delegate_task", "list_directory", "read_file",
                ],
            ),
        )
        assert_turn_passed(result)

    def test_delegate_with_category(self, lingwen_handler):
        """Delegate with explicit category mention."""
        result = send_message(
            lingwen_handler,
            "交给内容代理帮我整理一下 docs 目录的文档",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "delegate_task", "list_directory", "read_file",
                ],
            ),
        )
        assert_turn_passed(result)

    def test_delegate_colloquial(self, lingwen_handler):
        """Delegate in colloquial style."""
        result = send_message(
            lingwen_handler,
            "帮我把项目里的 README 重新写一下，内容更详细点",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "delegate_task", "read_file",
                ],
            ),
        )
        assert_turn_passed(result)

    def test_delegate_multistep(self, lingwen_handler):
        """Multi-step delegation instruction."""
        result = send_message(
            lingwen_handler,
            "先检查项目有哪些 markdown 文件，然后给每个文件加一行版权声明",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=[
                    "delegate_task", "list_directory", "search_files",
                ],
            ),
        )
        assert_turn_passed(result)
