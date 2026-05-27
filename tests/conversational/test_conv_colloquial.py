"""Conversational tests — colloquial / non-standard expressions.

Real humans on WeChat use slang, abbreviations, fragments, mixed
Chinese-English, and informal phrasing. These 20 tests verify the
LLM can still route to the correct tools despite messy input.

Run:
    BUTLER_RUN_REAL_API_SMOKE=1 PYTHONPATH=. \\
        pytest tests/conversational/test_conv_colloquial.py -v
"""

from __future__ import annotations

from tests.conversational.conftest_conversational import send_message
from tests.conversational.evaluation import ConversationRubric, assert_turn_passed


class TestColloquialMemo:
    """Memo creation with informal phrasing."""

    def test_omit_subject(self, live_minimax_handler):
        """Omitted subject — '记下来，明天开会'."""
        result = send_message(
            live_minimax_handler,
            "记下来，明天开会",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_abbreviation(self, live_minimax_handler):
        """Abbreviated — '明天3点会，别忘了'."""
        result = send_message(
            live_minimax_handler,
            "明天3点会，别忘了",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_modal_particles(self, live_minimax_handler):
        """With modal particles — '哎帮我记个事儿呗'."""
        result = send_message(
            live_minimax_handler,
            "哎帮我记个事儿呗，后天去拿快递",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_synonym_biewang(self, live_minimax_handler):
        """Synonym — '别让我忘了明天体检'."""
        result = send_message(
            live_minimax_handler,
            "别让我忘了明天体检",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_colloquial_time_dahoutian(self, live_minimax_handler):
        """Colloquial time — '大后天'."""
        result = send_message(
            live_minimax_handler,
            "大后天下午要去银行，记一下",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_question_plus_command(self, live_minimax_handler):
        """Question mixed with command."""
        result = send_message(
            live_minimax_handler,
            "能帮我记一下吗明天体检",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_command_tone(self, live_minimax_handler):
        """Imperative tone — '记！明天交材料'."""
        result = send_message(
            live_minimax_handler,
            "记！明天交材料",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_self_talk_style(self, live_minimax_handler):
        """Self-talk style."""
        result = send_message(
            live_minimax_handler,
            "我想想...帮我记个事，周六要去超市",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_chinese_english_mix(self, live_minimax_handler):
        """Mixed Chinese-English."""
        result = send_message(
            live_minimax_handler,
            "mark一下明天的meeting",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)

    def test_polite_request(self, live_minimax_handler):
        """Polite/verbose style."""
        result = send_message(
            live_minimax_handler,
            "不好意思，麻烦帮我记一下，下周三有个面试",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)


class TestColloquialExpense:
    """Expense tracking with informal phrasing."""

    def test_chinese_number(self, live_minimax_handler):
        """Chinese number — '花了三十五块'."""
        result = send_message(
            live_minimax_handler,
            "午饭花了三十五块",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)

    def test_unit_omitted(self, live_minimax_handler):
        """Unit omitted — '加油400'."""
        result = send_message(
            live_minimax_handler,
            "加油400",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)

    def test_multiple_expense_styles(self, live_minimax_handler):
        """Various phrasing — '打车28块钱'."""
        result = send_message(
            live_minimax_handler,
            "打车28块钱",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)

    def test_ultra_short(self, live_minimax_handler):
        """Ultra short — '午饭35'."""
        result = send_message(
            live_minimax_handler,
            "午饭35",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)

    def test_phone_bill(self, live_minimax_handler):
        """Phone bill — '充话费100'."""
        result = send_message(
            live_minimax_handler,
            "充话费100",
            rubric=ConversationRubric(expect_tool_called="expense_add"),
        )
        assert_turn_passed(result)


class TestColloquialContact:
    """Contact saving with informal phrasing."""

    def test_lazy_format(self, live_minimax_handler):
        """Lazy typing — '存个号码 李总 13900001234'."""
        result = send_message(
            live_minimax_handler,
            "存个号码 李总 13900001234",
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(result)

    def test_reverse_confirm(self, live_minimax_handler):
        """Reverse confirm style — '记了没？张三 13800001234'."""
        result = send_message(
            live_minimax_handler,
            "帮我存一下，赵老师 13600005678",
            rubric=ConversationRubric(expect_tool_called="contact_add"),
        )
        assert_turn_passed(result)


class TestColloquialHabit:
    """Habit operations with informal phrasing."""

    def test_colloquial_checkin(self, live_minimax_handler):
        """Informal check-in."""
        send_message(
            live_minimax_handler,
            "创建一个每天阅读的习惯",
            rubric=ConversationRubric(expect_tool_called="habit_create"),
        )
        result = send_message(
            live_minimax_handler,
            "今天读完了",
            rubric=ConversationRubric(expect_tool_called="habit_checkin"),
        )
        assert_turn_passed(result)

    def test_emoji_thanks(self, live_minimax_handler):
        """Gratitude with casual tone."""
        result = send_message(
            live_minimax_handler,
            "谢谢啦",
            rubric=ConversationRubric(
                expect_no_tool=True,
                reject_keywords=["error", "异常"],
            ),
        )
        assert result.response.strip()
        assert_turn_passed(result)

    def test_month_end_time(self, live_minimax_handler):
        """Colloquial time — '月底'."""
        result = send_message(
            live_minimax_handler,
            "月底之前要把报税弄完，帮我记着",
            rubric=ConversationRubric(expect_tool_called="memo_add"),
        )
        assert_turn_passed(result)
