"""R2-16 [H] silent_pass (last-resort 错误格式化降级) — error card 自身崩溃被静默吞.

`butler/gateway/locked_phases.py:483-484` (`_phase_format_error_card`):

    try:
        from butler.gateway.error_cards import format_error_card
        ...
        return format_error_card(...)
    except Exception:
        return None

问题:
- 整条 gateway 流程的**最后兜底** — 错误卡片系统本身崩溃时,
  `format_error_card` 的失败完全静默 (`return None`)
- caller `message_handler.py:522-525` 收到 None → 走通用
  `format_gateway_user_error(exc)`, 操作者只看到通用消息, **不知道 error card
  渲染器自身崩了**
- 真正的诊断信号被静默吞掉

修复:
- except Exception 改为 log at ERROR with exc_info, 再 return None
- 行为不变: caller 仍收 None, 仍 fallback 到 format_gateway_user_error
- 错误卡片渲染器的崩溃被记录, 操作者可在日志中诊断

行为保证:
1) format_error_card 抛异常 → _phase_format_error_card 返回 None (旧行为)
2) 同时 log at ERROR with exc_info (新行为, 操作者可见)
3) format_error_card 正常返回 → 不 log, 不污染
4) caller (message_handler) 行为不变: 仍用 format_gateway_user_error 兜底
"""

from __future__ import annotations

import logging

import pytest

from butler.gateway import locked_phases
from butler.gateway.locked_phases import _phase_format_error_card


@pytest.mark.unit
class TestErrorCardRendererFailure:
    """format_error_card 抛异常时, 失败必须被记录 (不再 silent)."""

    def test_returns_none_on_renderer_failure(self, monkeypatch):
        """renderer 失败 → 仍返回 None (caller fallback 不变)."""
        def _explode(*args, **kwargs):
            raise RuntimeError("template engine broken")
        monkeypatch.setattr(
            "butler.gateway.error_cards.format_error_card", _explode
        )
        result = _phase_format_error_card(RuntimeError("upstream"), 1.5)
        assert result is None, (
            "renderer 失败时仍应返回 None (caller 走通用兜底)"
        )

    def test_logs_error_with_exc_info_on_renderer_failure(self, monkeypatch, caplog):
        """renderer 失败必须 log at ERROR with exc_info (新行为, 审计要求)."""
        def _explode(*args, **kwargs):
            raise RuntimeError("template engine broken")
        monkeypatch.setattr(
            "butler.gateway.error_cards.format_error_card", _explode
        )
        with caplog.at_level(logging.DEBUG, logger="butler.gateway.locked_phases"):
            _phase_format_error_card(RuntimeError("upstream"), 1.5)
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            f"renderer 失败必须 log at ERROR, 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )
        assert any(r.exc_info is not None for r in error_records), (
            "renderer 失败的 ERROR log 必须含 exc_info (保留 traceback)"
        )
        # 关键词 "error card" 让操作者知道是 error card 渲染器挂了
        assert any(
            "error card" in r.message.lower() or "format" in r.message.lower()
            for r in error_records
        ), (
            f"ERROR log 应提及 error card 渲染器, 实际: "
            f"{[r.message for r in error_records]}"
        )

    def test_no_log_on_success(self, monkeypatch, caplog):
        """renderer 正常返回 → 不应有 ERROR log (避免 log spam)."""
        monkeypatch.setattr(
            "butler.gateway.error_cards.format_error_card",
            lambda *a, **kw: "card-content",
        )
        with caplog.at_level(logging.DEBUG, logger="butler.gateway.locked_phases"):
            result = _phase_format_error_card(RuntimeError("upstream"), 1.5)
        assert result == "card-content"
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records == [], (
            f"renderer 成功时不应有 ERROR log, 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )


@pytest.mark.unit
class TestImportFailure:
    """format_error_card 导入本身失败 (e.g. 模块被 monkeypatch 删除) 也必须 log."""

    def test_logs_error_when_import_fails(self, monkeypatch, caplog):
        """如果 error_cards 模块导入失败, 也应 log at ERROR."""
        # 隐藏 format_error_card 的 import 路径, 让 from ... import 抛 ImportError
        import sys

        # Patch the module-level import to raise
        orig_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

        def _patched_import(name, *args, **kwargs):
            if name == "butler.gateway.error_cards":
                raise ImportError("simulated: error_cards module missing")
            return orig_import(name, *args, **kwargs)

        # Restore: the test simulates module-level from-import failure inside
        # _phase_format_error_card. Easiest: delete the entry from sys.modules.
        monkeypatch.setitem(sys.modules, "butler.gateway.error_cards", None)
        with caplog.at_level(logging.DEBUG, logger="butler.gateway.locked_phases"):
            result = _phase_format_error_card(RuntimeError("upstream"), 1.5)
        assert result is None
        error_records = [r for r in caplog.records if r.levelno >= logging.ERROR]
        assert error_records, (
            f"import 失败时必须 log at ERROR, 实际: "
            f"{[(r.levelname, r.message) for r in caplog.records]}"
        )
