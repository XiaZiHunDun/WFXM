"""Dedicated asyncio loop for MCP SDK calls from sync Butler code."""

from __future__ import annotations

import asyncio
import atexit
import logging
import signal
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

logger = logging.getLogger(__name__)

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.RLock()
_atexit_registered = False
_signal_registered = False
_prev_signal_handlers: dict[int, Any] = {}
_shutdown_once = threading.Lock()
_shutdown_done = False


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread, _atexit_registered
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            try:
                loop.run_forever()
            finally:
                # 兜底: run_until_complete 调用 run_forever 退出后,
                # 关 loop 释放资源。
                try:
                    loop.close()
                except Exception:
                    pass

        _thread = threading.Thread(target=_run, daemon=True, name="butler-mcp-loop")
        _thread.start()
        _loop = loop
        if not _atexit_registered:
            atexit.register(_atexit_shutdown)
            _atexit_registered = True
        _register_signal_shutdown()
        return loop


def run_mcp_async(coro: Coroutine[Any, Any, T], *, timeout: float = 120.0) -> T:
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)


def shutdown_async_runner(*, timeout: float = 5.0) -> bool:
    """Stop the MCP async loop, cancel pending tasks, and join the thread.

    Returns True if the thread was cleanly joined within ``timeout``.
    Idempotent: safe to call multiple times; safe to call before
    ``_ensure_loop()`` was ever invoked.
    """
    global _loop, _thread
    with _lock:
        if _loop is None or _thread is None:
            return True
        loop = _loop
        thread = _thread

    # 1) Signal the loop to stop (thread-safe).
    try:
        loop.call_soon_threadsafe(loop.stop)
    except RuntimeError:
        pass  # loop already closed

    # 2) Join the thread with timeout (keep globals until join completes).
    thread.join(timeout=timeout)
    joined = not thread.is_alive()
    if not joined:
        logger.warning(
            "async_runner shutdown timeout: 守护线程未在 %.1fs 内退出, "
            "残留资源可能未被清理",
            timeout,
        )

    # 3) Cancel pending tasks and close the loop.
    try:
        pending = [t for t in asyncio.all_tasks(loop=loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            # Loop is no longer running (thread exited), so we must run
            # a short coroutine to drain cancellations.
            try:
                loop.run_until_complete(
                    asyncio.gather(*pending, return_exceptions=True)
                )
            except Exception as exc:
                logger.debug("async_runner task drain error: %s", exc)
    except Exception as exc:
        logger.debug("async_runner task cancel error: %s", exc)
    try:
        if not loop.is_closed():
            loop.close()
    except Exception as exc:
        logger.debug("async_runner loop close error: %s", exc)

    if joined:
        with _lock:
            if _loop is loop and _thread is thread:
                _loop = None
                _thread = None
    return joined


def _disconnect_mcp_connections() -> None:
    """Run MCP transport cleanup while the dedicated loop is still alive."""
    try:
        from butler.mcp.config import mcp_enabled

        if not mcp_enabled():
            return
        from butler.mcp.manager import get_manager

        get_manager().disconnect_all()
    except Exception as exc:
        logger.debug("MCP disconnect during shutdown: %s", exc)


def graceful_shutdown_mcp_stack(*, timeout: float = 5.0) -> bool:
    """Disconnect MCP stdio/http sessions, then stop the MCP asyncio loop."""
    global _shutdown_done
    with _shutdown_once:
        if _shutdown_done:
            return True
        _shutdown_done = True
    _disconnect_mcp_connections()
    return shutdown_async_runner(timeout=timeout)


def _register_signal_shutdown() -> None:
    """Register SIGTERM/SIGINT to drain MCP before loop teardown (R5-13)."""
    global _signal_registered
    with _lock:
        if _signal_registered:
            return
        _signal_registered = True

    def _handler(signum: int, frame: Any) -> None:
        try:
            graceful_shutdown_mcp_stack(timeout=5.0)
        except Exception as exc:
            logger.debug("async_runner signal shutdown error: %s", exc)
        prev = _prev_signal_handlers.get(signum)
        if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):
            try:
                prev(signum, frame)
            except Exception as exc:
                logger.debug("async_runner chained signal handler error: %s", exc)

    for sig_name in ("SIGTERM", "SIGINT"):
        sig = getattr(signal, sig_name, None)
        if sig is None:
            continue
        try:
            _prev_signal_handlers[sig] = signal.getsignal(sig)
            signal.signal(sig, _handler)
        except (ValueError, OSError) as exc:
            logger.debug("async_runner signal register %s skipped: %s", sig_name, exc)


def _atexit_shutdown() -> None:
    """atexit 钩子: 进程退出前清理 MCP 异步线程。

    用较短的 timeout (2s) 因为 atexit 阶段不应长时间阻塞进程退出。
    """
    try:
        global _shutdown_done
        with _shutdown_once:
            if _shutdown_done:
                return
            _shutdown_done = True
        _disconnect_mcp_connections()
        shutdown_async_runner(timeout=2.0)
    except Exception as exc:
        logger.debug("async_runner atexit shutdown error: %s", exc)
