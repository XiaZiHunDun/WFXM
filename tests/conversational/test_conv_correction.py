"""Conversational tests — correction and retraction.

Tests that the LLM handles user corrections, retractions, and
partial modifications gracefully across multi-turn conversations.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_correction.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestExpenseCorrection:
    """Corrections in expense tracking."""

    def test_immediate_amount_correction(self, live_minimax_handler):
        """'花了35' → '不对，是53'."""
        sk = "wechat:corr-exp-amt"
        send_message(
            live_minimax_handler, "午饭花了35",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r2 = send_message(
            live_minimax_handler, "不对，是53",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "expense_delete"],
            ),
        )
        assert_turn_passed(r2)

    def test_category_correction(self, live_minimax_handler):
        """'午饭花了30' → '这个应该算交通费'."""
        sk = "wechat:corr-exp-cat"
        send_message(
            live_minimax_handler, "午饭花了30",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r2 = send_message(
            live_minimax_handler, "这个应该算交通费，记错类别了",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_add", "expense_delete"],
            ),
        )
        assert_turn_passed(r2)

    def test_batch_delete(self, live_minimax_handler):
        """'把今天记的账都删了'."""
        sk = "wechat:corr-exp-batch"
        send_message(
            live_minimax_handler, "早餐10",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        send_message(
            live_minimax_handler, "午饭25",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        r3 = send_message(
            live_minimax_handler, "把今天记的账都删了",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["expense_delete", "expense_list"],
            ),
        )
        assert_turn_passed(r3)


class TestContactCorrection:
    """Corrections in contact management."""

    def test_phone_number_correction(self, live_minimax_handler):
        """'存一下张三电话 139...' → '打错了，是138...'."""
        sk = "wechat:corr-ct-phone"
        send_message(
            live_minimax_handler, "存一下张三电话 13900001111",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        r2 = send_message(
            live_minimax_handler, "打错了，应该是 13800002222",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_update", "contact_add"],
            ),
        )
        assert_turn_passed(r2)

    def test_name_correction(self, live_minimax_handler):
        """'存李四的电话' → '不是李四，是李思'."""
        sk = "wechat:corr-ct-name"
        send_message(
            live_minimax_handler, "存李四的电话 13700001234",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        r2 = send_message(
            live_minimax_handler, "不是李四，是李思，名字打错了",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["contact_update", "contact_add", "contact_delete"],
            ),
        )
        assert_turn_passed(r2)


class TestMemoCorrection:
    """Corrections in memo management."""

    def test_retract_memo(self, live_minimax_handler):
        """'记一下开会' → '算了不用记了'."""
        sk = "wechat:corr-memo-retract"
        send_message(
            live_minimax_handler, "记一下明天开会",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        r2 = send_message(
            live_minimax_handler, "算了不用记了",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_delete", "memo_update"],
            ),
        )
        assert_turn_passed(r2)

    def test_time_correction(self, live_minimax_handler):
        """'明天开会' → '不是明天，是后天'."""
        sk = "wechat:corr-memo-time"
        send_message(
            live_minimax_handler, "帮我记一下明天开会",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        r2 = send_message(
            live_minimax_handler, "不是明天，是后天",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_update", "memo_add"],
            ),
        )
        assert_turn_passed(r2)

    def test_partial_edit(self, live_minimax_handler):
        """'改一下刚才的备忘，加个提醒'."""
        sk = "wechat:corr-memo-partial"
        send_message(
            live_minimax_handler, "帮我记一下下周五交报告",
            session_key=sk,
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        r2 = send_message(
            live_minimax_handler, "刚才那个备忘帮我标成紧急的",
            session_key=sk,
            rubric=ConversationRubric(
                expect_any_tool_called=["memo_update"],
            ),
        )
        assert_turn_passed(r2)


class TestMistriggerRecovery:
    """Recovery from accidental tool triggers."""

    def test_deny_intent(self, live_minimax_handler):
        """'我没说要记账啊' — should not force execution."""
        result = send_message(
            live_minimax_handler,
            "我没说要记账啊",
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_not_what_i_meant(self, live_minimax_handler):
        """'我不是那个意思' — should not proceed with prior tool."""
        result = send_message(
            live_minimax_handler,
            "我不是那个意思",
            rubric=ConversationRubric(
                reject_keywords=["error"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)
