"""Sprint 16 TST-10-5 第八批: 4 prequeue/special-path 命令迁移测试.

迁移 4 个 inline 命令, 全部不在标准 slash dispatch 路径:
  - /停止   — pre-dispatch hook (运行中会话中断), message_handler.py:422-424 + 542
  - /继续   — pre-dispatch text rewriter (auto-continue 恢复), message_handler.py:426-433
  - /urgent — pre-queue priority tag (priority="now"), message_queue.py:78
  - /later  — pre-queue priority tag (priority="later"), message_queue.py:80

迁移要点 (与前 7 批不同):
  - 这 4 个**不是** slash dispatch 命令, 加 registry handler 无意义
  - 2 个 priority tag (/urgent /later) 根本不走 dispatch, 从 registry 移除
  - 2 个 pre-dispatch hook (/停止 /继续) 抽 helper 函数, pre-dispatch 仍需保留
  - 4 个 CommandDef 全部从 _register_defaults() 移除
  - _KNOWN_INLINE_COMMANDS 最终归零 (Sprint 11 baseline 30 → 0)
  - /停止 /继续 的 CommandDef 同步移除, 否则 test_no_unexpected_commands_need_handler 失败

覆盖: 静态契约 (4 lookup None) + auto_continue rewrite 行为 + prequeue interrupt 行为
      + 集合归零 + priority tag 文档注释
"""

from __future__ import annotations

import inspect
from unittest.mock import MagicMock, patch

import pytest

from butler.gateway.command_registry import lookup


# ── 静态契约 ──


class TestStaticContract:
    """4 个 prequeue 命令应从 registry 完全移除, lookup 返 None."""

    @pytest.mark.parametrize(
        "name",
        ["/继续", "/停止", "/urgent", "/later"],
    )
    def test_lookup_returns_none_for_prequeue_command(self, name):
        assert lookup(name) is None, (
            f"{name} 应从 registry 移除 (prequeue priority tag 或 pre-dispatch hook, "
            f"不是 slash dispatch 命令)"
        )


# ── auto_continue rewrite helper ──


class TestAutoContinueRewrite:
    """apply_auto_continue_rewrite 应包装 resolve_auto_continue_user_message.

    行为契约:
      - 有 pending (且 marker 匹配): 返新 text
      - 无 pending 或 marker 不匹配: 返 None (text 不变)
      - 异常: 返 None + logger.debug (与原 try/except 行为一致)
    """

    def test_has_pending_returns_new_text(self):
        from butler.gateway.handler_helpers import apply_auto_continue_rewrite

        with patch(
            "butler.core.auto_continue.resolve_auto_continue_user_message",
            return_value="[AUTO-CONTINUE — resume...",
        ) as m:
            result = apply_auto_continue_rewrite("wx:u1:", "继续")
        assert result == "[AUTO-CONTINUE — resume..."
        m.assert_called_once_with("wx:u1:", "继续")

    def test_no_pending_returns_none(self):
        from butler.gateway.handler_helpers import apply_auto_continue_rewrite

        with patch(
            "butler.core.auto_continue.resolve_auto_continue_user_message",
            return_value=None,
        ):
            result = apply_auto_continue_rewrite("wx:u1:", "继续")
        assert result is None

    def test_exception_returns_none_and_logs_debug(self):
        from butler.gateway.handler_helpers import apply_auto_continue_rewrite

        with patch(
            "butler.core.auto_continue.resolve_auto_continue_user_message",
            side_effect=RuntimeError("boom"),
        ), patch("butler.gateway.handler_helpers.logger") as logger_mock:
            result = apply_auto_continue_rewrite("wx:u1:", "继续")
        assert result is None
        # 原 inline 行为是 logger.debug
        logger_mock.debug.assert_called()

    def test_helper_is_in_handler_helpers(self):
        """helper 必须定义在 butler.gateway.handler_helpers, 供 message_handler 调用."""
        from butler.gateway import handler_helpers

        assert hasattr(handler_helpers, "apply_auto_continue_rewrite")
        assert callable(handler_helpers.apply_auto_continue_rewrite)


# ── prequeue interrupt format method ──


class TestPrequeueInterruptFormat:
    """_format_prequeue_interrupt_reply 抽自 message_handler.py:422-424.

    行为契约:
      - 调用 self._interrupt_session_loop(session_key)
      - 返 "已请求停止当前会话任务（含进行中的委派）。"
      - _interrupt_session_loop 抛异常: 不应阻断返消息 (logger.debug + 返消息)
    """

    def _make_handler(self) -> MagicMock:
        """Build a mock message handler instance with _interrupt_session_loop + _sessions."""
        handler = MagicMock()
        handler._sessions = {}
        return handler

    def test_returns_interrupt_message(self):
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = self._make_handler()
        result = ButlerMessageHandler._format_prequeue_interrupt_reply(
            handler, "wx:u1:",
        )
        assert "已请求停止" in result
        assert "委派" in result
        handler._interrupt_session_loop.assert_called_once_with("wx:u1:")

    def test_interrupt_exception_still_returns_message(self):
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = self._make_handler()
        handler._interrupt_session_loop.side_effect = RuntimeError("interrupt-fail")
        # 不应抛异常, 仍返消息
        with patch("butler.gateway.message_handler.logger") as logger_mock:
            result = ButlerMessageHandler._format_prequeue_interrupt_reply(
                handler, "wx:u1:",
            )
        assert "已请求停止" in result
        logger_mock.debug.assert_called()

    def test_no_session_loop_present(self):
        """session 不在 _sessions 中: 不应 crash, 仍返消息."""
        from butler.gateway.message_handler import ButlerMessageHandler

        handler = self._make_handler()
        # _interrupt_session_loop 内会处理 None 情况 (原行为)
        result = ButlerMessageHandler._format_prequeue_interrupt_reply(
            handler, "wx:u1:",
        )
        assert "已请求停止" in result
        handler._interrupt_session_loop.assert_called_once_with("wx:u1:")


# ── 集合归零 ──


class TestInlineSetEmpty:
    """Sprint 11 baseline 30 → 0: _KNOWN_INLINE_COMMANDS 应为空 frozenset."""

    def test_known_inline_set_is_empty(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        assert _KNOWN_INLINE_COMMANDS == frozenset(), (
            f"TST-10-5 全部迁移完成, _KNOWN_INLINE_COMMANDS 应为空, "
            f"实际: {sorted(_KNOWN_INLINE_COMMANDS)}"
        )

    def test_no_4_prequeue_names_in_whitelist(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        for name in ("/继续", "/停止", "/urgent", "/later"):
            assert name not in _KNOWN_INLINE_COMMANDS, (
                f"{name} 仍 in _KNOWN_INLINE_COMMANDS, 迁移未完成"
            )


# ── inline command still dispatches (迁移完成, 改为空集断言) ──


class TestInlineSetZeroCompletion:
    """TST-10-5 完成: test_inline_command_still_dispatches 改为显式空集断言.

    原测试: for name in _KNOWN_INLINE_COMMANDS: assert lookup(name) is not None
    迁移后: _KNOWN_INLINE_COMMANDS 为空, 改为显式 frozenset() 断言.
    """

    def test_known_inline_set_final_assertion(self):
        from tests.test_command_registry import _KNOWN_INLINE_COMMANDS

        # 显式断言: 迁移完成, 集合为空
        assert _KNOWN_INLINE_COMMANDS == frozenset()
        # 防护: 防止有人误把名字加回来
        assert len(_KNOWN_INLINE_COMMANDS) == 0


# ── priority tag 文档注释 ──


class TestPriorityTagDoc:
    """classify_inbound_priority docstring 应说明 /urgent /later 是 priority tag, 不走 dispatch."""

    def test_docstring_mentions_priority_tag(self):
        from butler.gateway.message_queue import classify_inbound_priority

        doc = inspect.getdoc(classify_inbound_priority) or ""
        assert "priority" in doc.lower(), (
            f"classify_inbound_priority docstring 应说明 priority tag 语义, 实际: {doc!r}"
        )


# ── 集成: 4 个命令整体行为 ──


class TestOverallMigration:
    """综合验证 4 个命令都被正确迁移出 inline 路径."""

    def test_4_commands_not_in_registry(self):
        """4 个命令都不在 registry 中."""
        for name in ("/继续", "/停止", "/urgent", "/later"):
            assert lookup(name) is None, f"{name} 仍 in registry"

    def test_help_text_no_longer_shows_4_commands(self):
        """format_registry_help 不应再列出 4 个命令 (它们不是 registry 命令).

        注意: ``/停止`` 是 ``/停止循环`` 的子串 (子串匹配假阳性), 用 word boundary 精确匹配.
        """
        import re

        from butler.gateway.command_registry import format_registry_help

        help_text = format_registry_help()
        for name in ("/继续", "/停止", "/urgent", "/later"):
            # 用正则 word boundary 避免 /停止 误匹配 /停止循环
            pattern = re.compile(rf"(^|\s){re.escape(name)}(\s|$|/)")
            assert not pattern.search(help_text), (
                f"{name} 不应出现在 format_registry_help 中 (不是 registry 命令). "
                f"实际 help_text: {help_text!r}"
            )

    def test_4_commands_have_no_e2e_path(self):
        """4 个命令没有 dispatch path (lookup None → dispatch 返 (False, None))."""
        from butler.gateway.command_registry import (
            CommandContext,
            dispatch,
        )

        for name in ("/继续", "/停止", "/urgent", "/later"):
            ctx = CommandContext(
                cmd=name,
                arg="",
                session_key="wx:u1:",
                platform="wechat",
                external_id="u1",
                orchestrator=MagicMock(),
                session_registry=MagicMock(),
            )
            handled, result = dispatch(ctx)
            assert handled is False, f"{name} 仍被 dispatch 视为 handled"
            assert result is None
