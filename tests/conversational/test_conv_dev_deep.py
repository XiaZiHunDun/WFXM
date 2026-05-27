"""Conversational tests — deep development scenarios.

Tests advanced dev interactions: code search, file inspection,
delegation with specific roles, technical decision recording,
progress reporting, and multi-project awareness.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_dev_deep.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestCodeSearch:
    """Code searching and inspection."""

    def test_search_keyword(self, lingwen_handler):
        """'项目里有没有用到 requests 库'."""
        result = send_message(
            lingwen_handler,
            "项目里有没有 CONV_TEST_MARKER 这个关键词",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["search_files", "read_file"],
            ),
        )
        assert_turn_passed(result)

    def test_directory_listing(self, lingwen_handler):
        """'项目目录下有什么文件'."""
        result = send_message(
            lingwen_handler,
            "docs 目录下有什么",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory"],
            ),
        )
        assert_turn_passed(result)

    def test_read_specific_file(self, lingwen_handler):
        """'看看 README.md 的内容'."""
        result = send_message(
            lingwen_handler,
            "看看 README.md 的内容",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file"],
            ),
        )
        assert_turn_passed(result)

    def test_project_structure(self, lingwen_handler):
        """'项目结构是怎样的'."""
        result = send_message(
            lingwen_handler,
            "项目的目录结构是什么样的",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["list_directory"],
            ),
        )
        assert_turn_passed(result)


class TestDelegationRoles:
    """Delegation with specific role mentions."""

    def test_code_review_delegate(self, lingwen_handler):
        """'帮我审查一下最近的代码改动'."""
        result = send_message(
            lingwen_handler,
            "帮我审查一下项目代码",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "read_file", "list_directory"],
            ),
        )
        assert_turn_passed(result)

    def test_doc_generation_delegate(self, lingwen_handler):
        """'帮灵文项目生成一个文档'."""
        result = send_message(
            lingwen_handler,
            "帮灵文项目在 docs 目录写一个说明文档",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task"],
            ),
        )
        assert_turn_passed(result)

    def test_batch_operation_delegate(self, lingwen_handler):
        """'给所有文件加上文件头注释'."""
        result = send_message(
            lingwen_handler,
            "帮我给项目里的文件都加上一行版权声明",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["delegate_task", "list_directory"],
            ),
        )
        assert_turn_passed(result)


class TestTechnicalMemory:
    """Recording technical decisions and recalling them."""

    def test_record_decision(self, lingwen_handler):
        """'决定不用 Redis，改用本地缓存'."""
        result = send_message(
            lingwen_handler,
            "决定不用 Redis，改用本地缓存，帮我记住",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_remember"],
            ),
        )
        assert_turn_passed(result)

    def test_recall_past_decision(self, lingwen_handler):
        """'之前做了什么决定'."""
        result = send_message(
            lingwen_handler,
            "之前灵文项目做过什么技术决定",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["butler_recall", "search_project_knowledge"],
            ),
        )
        assert_turn_passed(result)


class TestProjectQueries:
    """Project-level queries and overview."""

    def test_project_health_check(self, lingwen_handler):
        """'检查一下项目有没有问题'."""
        result = send_message(
            lingwen_handler,
            "检查一下项目状况",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                reject_keywords=["traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_env_config(self, lingwen_handler):
        """'看看项目配置'."""
        result = send_message(
            lingwen_handler,
            "看看项目的配置文件",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file", "list_directory"],
            ),
        )
        assert_turn_passed(result)

    def test_progress_report(self, lingwen_handler):
        """'帮我整理一下最近做了什么'."""
        result = send_message(
            lingwen_handler,
            "帮我看看项目最近有什么变化",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                expect_any_tool_called=["read_file", "list_directory", "butler_recall"],
                reject_keywords=["traceback"],
            ),
        )
        assert_turn_passed(result)


class TestTechConsulting:
    """General technical questions."""

    def test_architecture_question(self, lingwen_handler):
        """'你觉得这个架构合理吗'."""
        result = send_message(
            lingwen_handler,
            "你觉得这个项目的架构合理吗",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                reject_keywords=["traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_error_inquiry(self, lingwen_handler):
        """'上次有什么错误'."""
        result = send_message(
            lingwen_handler,
            "项目最近有没有什么问题或错误",
            session_key="wechat:conv-dev",
            rubric=ConversationRubric(
                reject_keywords=["traceback"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)
