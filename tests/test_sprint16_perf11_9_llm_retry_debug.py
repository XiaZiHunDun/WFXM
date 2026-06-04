"""Sprint 16 PERF-11-9: butler.core.llm_retry 11 处无条件 logger.debug 调优.

bug: butler/core/llm_retry.py
  - LLM 路径每个 attempt 跑 4 个 try/except: logger.debug 块
  - logger.debug() 内部已做 isEnabledFor 检查, 但调用栈 + 异常处理
    的 setup 仍是无条件开销
  - 当 DEBUG 关闭 (生产默认) 时, 11 个 logger.debug 调用每次都跑过
    logger.isEnabledFor() 内部分支

修复: 把 11 处 try/except: logger.debug 替换为 ``_safe_call(fn, msg)``,
       集中做 isEnabledFor() 短路 + 错误日志。 当 debug 关闭时,
       整个 try/except 都被跳过, 不仅省 logger.debug 一次方法调用,
       还省 sys.settrace / exc_info 路径。
"""

from __future__ import annotations

import inspect
import logging
from typing import Any
from unittest.mock import MagicMock

import pytest

from butler.core import llm_retry
from butler.core.llm_retry import call_llm_with_retry
from butler.core.loop_types import LoopCallbacks, LoopConfig


# ── 静态契约: 必须有 _safe_call 辅助, 且 11 处 try/except 模式已重构 ──


class TestStaticContract:
    def test_safe_call_helper_exists(self):
        """llm_retry 模块应导出 ``_safe_call`` 帮助函数集中处理 try/except+debug。"""
        assert hasattr(llm_retry, "_safe_call"), (
            "llm_retry 应提供 _safe_call 辅助函数集中处理 try/except+debug "
            "(PERF-11-9: 取代 11 处内联 logger.debug 模式)"
        )
        assert callable(llm_retry._safe_call)

    def test_safe_call_short_circuits_when_debug_disabled(self):
        """当 logger.isEnabledFor(DEBUG) == False 时, _safe_call 应完全跳过 fn。"""
        call_count = {"n": 0}

        def should_not_run() -> Any:
            call_count["n"] += 1
            return "ran"

        with pytest.MonkeyPatch.context() as mp:
            # 把 logger 替换为 isEnabledFor 永远 False 的 mock
            fake_logger = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
            fake_logger.isEnabledFor.return_value = False
            mp.setattr(llm_retry, "logger", fake_logger)
            result = llm_retry._safe_call(should_not_run, "test msg")
        assert result is None, "_safe_call 在 debug 关闭时应返回 None (不跑 fn)"
        assert call_count["n"] == 0, (
            f"debug 关闭时 fn 不应被调用, 实际调了 {call_count['n']} 次"
        )

    def test_safe_call_runs_fn_and_returns_when_debug_enabled(self):
        """debug 开启时, _safe_call 跑 fn 并返回结果。"""
        with pytest.MonkeyPatch.context() as mp:
            fake_logger = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
            fake_logger.isEnabledFor.return_value = True
            mp.setattr(llm_retry, "logger", fake_logger)
            result = llm_retry._safe_call(lambda: 42, "test msg")
        assert result == 42

    def test_safe_call_swallows_exception_and_logs(self):
        """debug 开启时, fn 抛异常应被 _safe_call 吞掉并 logger.debug。"""
        def boom() -> Any:
            raise RuntimeError("kaboom")

        with pytest.MonkeyPatch.context() as mp:
            fake_logger = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
            fake_logger.isEnabledFor.return_value = True
            mp.setattr(llm_retry, "logger", fake_logger)
            result = llm_retry._safe_call(boom, "test msg: %s")
        assert result is None
        fake_logger.debug.assert_called_once()
        # 验证异常被传到 logger.debug 的 args
        call_args = fake_logger.debug.call_args
        assert "kaboom" in str(call_args), call_args

    def test_call_llm_uses_safe_call_pattern(self):
        """call_llm_with_retry 函数体应不含内联 try/except: logger.debug 模式。"""
        source = inspect.getsource(call_llm_with_retry)
        # 旧模式: try/except 内联 + logger.debug(...)
        # 新模式: 应该是 _safe_call(...)
        import re

        inline_pattern = re.compile(
            r"except Exception as \w+:\s*\n\s*logger\.debug\(",
            re.MULTILINE,
        )
        matches = inline_pattern.findall(source)
        assert len(matches) == 0, (
            f"call_llm_with_retry 仍有 {len(matches)} 处内联 "
            f"try/except: logger.debug 模式未重构 (PERF-11-9)。"
        )


# ── 行为契约: call_llm_with_retry 仍正常工作 ──


def _fake_client(*, content: str = "ok", raise_exc: Exception | None = None) -> MagicMock:
    """构造一个 fake LLMClient, complete() 返回给定 content。"""
    client = MagicMock()  # noqa: magicmock-no-spec — complex facade, spec= 收益低
    client.provider_name = "fake"
    client.model = "fake-model"
    if raise_exc is not None:
        client.complete.side_effect = raise_exc
        client.stream.side_effect = raise_exc
    else:
        from butler.transport.types import NormalizedResponse

        resp = NormalizedResponse(content=content, finish_reason="stop")
        client.complete.return_value = resp
        client.stream.return_value = resp
    return client


@pytest.fixture
def base_config() -> LoopConfig:
    return LoopConfig(max_retries=1, stream=False, max_empty_content_retries=0)


@pytest.fixture
def base_callbacks() -> LoopCallbacks:
    return LoopCallbacks()


@pytest.fixture
def no_prepare() -> Any:
    return lambda: [{"role": "user", "content": "hi"}]


class TestCallLlmWithRetryBehavior:
    def test_happy_path_returns_response(
        self, base_config, base_callbacks, no_prepare, monkeypatch,
    ):
        """happy path: LLM 返回 content → call_llm_with_retry 返回 (resp, False)。"""
        # 关掉所有 optional dependency (避免它们的 import 失败路径)
        monkeypatch.setenv("BUTLER_DISABLE_EXPERIMENTAL_CACHE", "1")
        client = _fake_client(content="hello")
        diagnostics: dict = {}
        result, interrupted = call_llm_with_retry(
            client=client,
            config=base_config,
            callbacks=base_callbacks,
            tools=[],
            messages=[],
            diagnostics=diagnostics,
            prepare_messages=no_prepare,
            compress_messages=lambda msgs: msgs,
            interrupt_check=lambda: False,
            try_activate_fallback=lambda: False,
            empty_retries=[0],
        )
        assert interrupted is False
        assert result is not None
        assert result.content == "hello"

    def test_interrupt_returns_immediately(
        self, base_config, base_callbacks, no_prepare, monkeypatch,
    ):
        """interrupt_check 立即 True → 返回 (None, True), 不调 LLM。"""
        monkeypatch.setenv("BUTLER_DISABLE_EXPERIMENTAL_CACHE", "1")
        client = _fake_client()
        result, interrupted = call_llm_with_retry(
            client=client,
            config=base_config,
            callbacks=base_callbacks,
            tools=[],
            messages=[],
            diagnostics={},
            prepare_messages=no_prepare,
            compress_messages=lambda msgs: msgs,
            interrupt_check=lambda: True,
            try_activate_fallback=lambda: False,
            empty_retries=[0],
        )
        assert result is None
        assert interrupted is True
        client.complete.assert_not_called()
        client.stream.assert_not_called()
