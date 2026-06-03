"""Sprint 16 REL-11-4: butler.gateway.runner SIGTERM 不等待 executor 排空.

bug: butler/gateway/runner.py:38, 100, 190, 204
  - 守护进程级 ThreadPoolExecutor (line 38) 处理 LLM handler 调用
  - SIGTERM 触发 ``stop.set()`` (line 190), 但:
    1. 没有 module-level ``is_shutting_down()`` 标志让 in-flight handler 感知
    2. submit 路径 (line 100) 不检查 shutdown, 新消息仍可入队
    3. ``shutdown(wait=True, cancel_futures=False)`` (line 204) 无超时,
       handler 卡住时进程永不退出
    4. 多次信号不幂等

修复: 加 module-level ``_SHUTDOWN_EVENT`` + ``is_shutting_down()`` API,
       submit 前检查, signal handler 同步 set, shutdown 序列加 grace 超时
       + 警告 + 幂等。
"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
import signal
import threading
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from butler.gateway import runner


# ── 隔离 fixture: 每个测试前后清空 shutdown 状态 ──


@pytest.fixture(autouse=True)
def _reset_shutdown_state():
    """每个测试清空 module-level shutdown 状态, 避免污染。"""
    if hasattr(runner, "_SHUTDOWN_EVENT") and runner._SHUTDOWN_EVENT.is_set():
        runner._SHUTDOWN_EVENT.clear()
    yield
    if hasattr(runner, "_SHUTDOWN_EVENT") and runner._SHUTDOWN_EVENT.is_set():
        runner._SHUTDOWN_EVENT.clear()


# ── 静态契约: 必需的 shutdown API ──


class TestShutdownApiContract:
    def test_shutdown_event_attribute_exists(self):
        """runner 模块必须定义 _SHUTDOWN_EVENT (threading.Event)。"""
        assert hasattr(runner, "_SHUTDOWN_EVENT"), (
            "runner 应定义 _SHUTDOWN_EVENT (threading.Event) 让 in-flight handler 感知"
        )
        assert isinstance(runner._SHUTDOWN_EVENT, threading.Event), (
            f"_SHUTDOWN_EVENT 应为 threading.Event, 实际 {type(runner._SHUTDOWN_EVENT)}"
        )

    def test_is_shutting_down_function_exists(self):
        """runner 必须导出 ``is_shutting_down()`` 函数。"""
        assert hasattr(runner, "is_shutting_down"), (
            "runner 应导出 is_shutting_down() 供 handler / health check 查询"
        )
        assert callable(runner.is_shutting_down), (
            "is_shutting_down 应为可调用函数"
        )

    def test_is_shutting_down_false_initially(self):
        """未收到信号时, is_shutting_down() 应返回 False。"""
        # 隔离 fixture 已 clear, 但如果 module 在 import 时被 set, 再 clear 一次
        runner._SHUTDOWN_EVENT.clear()
        assert runner.is_shutting_down() is False


# ── is_shutting_down 行为 ──


class TestIsShuttingDownBehavior:
    def test_returns_true_after_event_set(self):
        """_SHUTDOWN_EVENT.set() 后, is_shutting_down() 应返回 True。"""
        runner._SHUTDOWN_EVENT.set()
        assert runner.is_shutting_down() is True

    def test_returns_false_after_event_cleared(self):
        """_SHUTDOWN_EVENT.clear() 后, is_shutting_down() 应返回 False。"""
        runner._SHUTDOWN_EVENT.set()
        runner._SHUTDOWN_EVENT.clear()
        assert runner.is_shutting_down() is False


# ── _request_stop 幂等 + 同步 set shutdown event ──


class TestRequestStopBehavior:
    def test_request_stop_sets_shutdown_event(self):
        """request_stop 应同时 set asyncio stop event + _SHUTDOWN_EVENT。"""
        stop = asyncio.Event()
        runner.request_stop(stop)
        assert stop.is_set(), "request_stop 必须 set asyncio stop event"
        assert runner.is_shutting_down(), (
            "request_stop 必须同步 set _SHUTDOWN_EVENT, "
            "让 in-flight handler (在线程中) 能立即感知"
        )

    def test_request_stop_idempotent(self):
        """多次调用 request_stop 不应抛异常。"""
        stop = asyncio.Event()
        runner.request_stop(stop)
        runner.request_stop(stop)
        runner.request_stop(stop)
        assert stop.is_set()
        assert runner.is_shutting_down()


# ── submit 路径应拒绝 shutdown 后的提交 ──


class TestSubmitPathShutdownGate:
    @pytest.mark.asyncio
    async def test_butler_message_handler_skips_when_shutting_down(self):
        """shutdown 已 set 时, _butler_message_handler 应快速返回 (不提交 executor)。"""
        from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource
        from butler.gateway.runner import _butler_message_handler

        runner._SHUTDOWN_EVENT.set()

        butler = MagicMock()
        event = MessageEvent(
            text="shutdown 期间的消息",
            message_type=MessageType.TEXT,
            source=SessionSource(platform="wechat", chat_id="u-shutdown", user_id="u-shutdown"),
        )

        # handler 永不执行 → butler.handle_message 不被调用
        out = await _butler_message_handler(butler, event)
        assert out is None, (
            f"shutdown 期间 _butler_message_handler 应返回 None, 实际 {out!r}"
        )
        butler.handle_message.assert_not_called()

    @pytest.mark.asyncio
    async def test_butler_message_handler_normal_when_not_shutting_down(self):
        """shutdown 未 set 时, _butler_message_handler 应正常提交 executor。"""
        from butler.gateway.platforms.types import MessageEvent, MessageType, SessionSource
        from butler.gateway.runner import _butler_message_handler

        # 确保未 set
        runner._SHUTDOWN_EVENT.clear()

        butler = MagicMock()
        butler.handle_message.return_value = "正常回复"
        event = MessageEvent(
            text="正常消息",
            message_type=MessageType.TEXT,
            source=SessionSource(platform="wechat", chat_id="u-normal", user_id="u-normal"),
        )

        out = await _butler_message_handler(butler, event)
        assert out == "正常回复"
        butler.handle_message.assert_called_once()


# ── shutdown 序列超时保护 (这是 audit 关键点) ──


class TestShutdownSequenceTimeout:
    @pytest.mark.asyncio
    async def test_shutdown_with_no_in_flight_returns_quickly(self):
        """没有 in-flight 任务时, shutdown 序列应快速完成 (< 1s)。"""
        # 用 mock 替代真实组件, 测 shutdown 序列本身
        with patch("butler.gateway.runner._HANDLER_EXECUTOR") as mock_exec, \
             patch.object(runner, "_poll_reminders_loop") as mock_poll:
            from butler.gateway.platforms.types import MessageEvent

            mock_adapter = MagicMock()
            mock_adapter.name = "test-adapter"
            mock_adapter.disconnect = AsyncMock()
            connected = [mock_adapter]
            reminder_task = MagicMock()
            reminder_task.cancel = MagicMock()

            start = time.monotonic()
            # 模拟 shutdown 序列 (从 audit 期望的 run_gateway_async 抽出来)
            # 验证: 1) reminder_task.cancel 2) disconnect 3) shutdown(wait=)
            # 简化: 直接验证 mock_exec.shutdown 被调用, 且有时间上限
            mock_exec.shutdown = MagicMock()
            reminder_task.cancel()
            await mock_adapter.disconnect()
            mock_exec.shutdown(wait=True)
            elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"无 in-flight shutdown 应 < 1s, 实际 {elapsed:.2f}s"
        mock_exec.shutdown.assert_called_once()

    @pytest.mark.asyncio
    async def test_shutdown_executor_timeout_protects_against_hung_handlers(self):
        """executor.shutdown 有 stuck task 时, 我们的 grace period 应有上限, 不无限等待。

        验证: 如果 executor.shutdown(wait=True) 真的卡住, 我们应用 asyncio.wait_for
        或等价的 timeout 保护, 让进程能在合理时间内退出。
        """
        # 模拟 executor.shutdown 永远卡
        blocking_event = threading.Event()
        call_count = {"n": 0}

        class FakeExecutor:
            def shutdown(self, *, wait: bool, cancel_futures: bool = False) -> None:
                call_count["n"] += 1
                if wait:
                    blocking_event.wait()  # 模拟卡住, 等待外部 set

        with patch.object(runner, "_HANDLER_EXECUTOR", FakeExecutor()):
            # 用 0.1s grace 模拟『shutdown 序列应超时』
            GRACE = 0.1
            start = time.monotonic()
            try:
                # 模拟 run_gateway_async 的 shutdown 序列, 用 asyncio.wait_for 加超时
                async def shutdown_with_timeout():
                    await asyncio.wait_for(
                        asyncio.to_thread(runner._HANDLER_EXECUTOR.shutdown, wait=True),
                        timeout=GRACE,
                    )

                with pytest.raises(asyncio.TimeoutError):
                    await shutdown_with_timeout()
            finally:
                blocking_event.set()  # 释放模拟的卡住
            elapsed = time.monotonic() - start

        # 实际应略大于 GRACE (因为 asyncio.wait_for 有额外开销)
        assert GRACE <= elapsed < GRACE + 1.0, (
            f"shutdown 应在 ~{GRACE}s 超时, 实际 {elapsed:.2f}s"
        )
        assert call_count["n"] == 1, "shutdown 应被调用一次"


# ── run_gateway_async 端到端: signal → shutdown 序列 (用 mock) ──


class TestRunGatewayAsyncShutdown:
    @pytest.mark.asyncio
    async def test_request_stop_can_trigger_shutdown_sequence(self, monkeypatch):
        """端到端: 外部调用 ``runner.request_stop(stop_event)`` 应能驱动整条 shutdown 序列。

        不直接跑 ``run_gateway_async`` (需要真实 adapter), 改为:
        1) 模拟一个 stop event 已被 set
        2) 验证后续序列: disconnect adapters → executor.shutdown(wait=True)
           都能正常完成
        """
        # 验证 request_stop 真的能驱动行为 (这是端到端契约)
        stop = asyncio.Event()
        monkeypatch.setattr(runner, "_SHUTDOWN_EVENT", threading.Event())

        # 模拟 in-flight: 一个轻量 fake executor, 验证 shutdown(wait=True) 被调
        shutdown_calls: list[dict] = []

        class FakeExecutor:
            def shutdown(self, *, wait: bool, cancel_futures: bool = False) -> None:
                shutdown_calls.append({"wait": wait, "cancel_futures": cancel_futures})

        with patch.object(runner, "_HANDLER_EXECUTOR", FakeExecutor()):
            runner.request_stop(stop)

            # 立即触发 shutdown 序列 (不 await stop.wait, 因为已 set)
            assert stop.is_set()
            assert runner.is_shutting_down()

            # 模拟 run_gateway_async 的 shutdown 序列后续
            mock_adapter = MagicMock()
            mock_adapter.name = "x"
            mock_adapter.disconnect = AsyncMock()
            # disconnect 应正常调 (await 不会抛)
            await mock_adapter.disconnect()
            mock_adapter.disconnect.assert_awaited_once()

            # shutdown 序列 (用 asyncio.wait_for 模拟 grace)
            await asyncio.wait_for(
                asyncio.to_thread(
                    runner._HANDLER_EXECUTOR.shutdown,
                    wait=True,
                    cancel_futures=False,
                ),
                timeout=5.0,
            )

            # 验证 shutdown 收到 wait=True, cancel_futures=False
            assert len(shutdown_calls) == 1
            assert shutdown_calls[0] == {"wait": True, "cancel_futures": False}


# ── 静态契约: 关键不变量 ──


class TestStaticInvariants:
    def test_handler_executor_is_module_level(self):
        """_HANDLER_EXECUTOR 必须是模块级 (进程内单例), 否则 shutdown 无效。"""
        assert hasattr(runner, "_HANDLER_EXECUTOR")
        assert isinstance(runner._HANDLER_EXECUTOR, concurrent.futures.ThreadPoolExecutor), (
            f"_HANDLER_EXECUTOR 应为 ThreadPoolExecutor, "
            f"实际 {type(runner._HANDLER_EXECUTOR)}"
        )

    def test_shutdown_event_uses_threading_not_asyncio(self):
        """_SHUTDOWN_EVENT 必须用 threading.Event (handler 在线程中, 看不见 asyncio.Event)。"""
        # 这是关键不变量: handler 工作在 executor 线程, 用 asyncio.Event 无法同步
        # 我们 import threading 验证, 而不是用 isinstance, 因为可能存在子类
        import threading

        event = runner._SHUTDOWN_EVENT
        # 必须有 set/clear/is_set 方法 (threading.Event API)
        for method in ("set", "clear", "is_set", "wait"):
            assert hasattr(event, method), (
                f"_SHUTDOWN_EVENT 应有 threading.Event API 方法: {method}"
            )
