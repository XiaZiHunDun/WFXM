"""MCP async runner shutdown helpers (P0-A)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def close_event_loop_safe(loop: asyncio.AbstractEventLoop) -> None:
    def _run() -> None:
        loop.close()

    safe_best_effort(_run, label="async_runner.close_loop", default=None)


def drain_pending_tasks_safe(loop: asyncio.AbstractEventLoop) -> None:
    def _run() -> None:
        pending = [t for t in asyncio.all_tasks(loop=loop) if not t.done()]
        for task in pending:
            task.cancel()
        if pending:
            loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))

    safe_best_effort(_run, label="async_runner.drain_tasks", default=None)


def close_loop_if_open_safe(loop: asyncio.AbstractEventLoop) -> None:
    def _run() -> None:
        if not loop.is_closed():
            loop.close()

    safe_best_effort(_run, label="async_runner.close_if_open", default=None)


def disconnect_mcp_connections_safe() -> None:
    def _run() -> None:
        from butler.mcp.config import mcp_enabled

        if not mcp_enabled():
            return
        from butler.mcp.manager import get_manager

        get_manager().disconnect_all()

    safe_best_effort(_run, label="async_runner.mcp_disconnect", default=None)


def signal_shutdown_safe() -> None:
    def _run() -> None:
        from butler.mcp.async_runner import graceful_shutdown_mcp_stack

        graceful_shutdown_mcp_stack(timeout=5.0)

    safe_best_effort(_run, label="async_runner.signal_shutdown", default=None)


def chain_signal_handler_safe(prev: Any, signum: int, frame: Any) -> None:
    import signal

    def _run() -> None:
        if callable(prev) and prev not in (signal.SIG_DFL, signal.SIG_IGN):
            prev(signum, frame)

    safe_best_effort(_run, label="async_runner.chain_signal", default=None)


def atexit_shutdown_safe() -> None:
    def _run() -> None:
        from butler.mcp import async_runner as mod

        with mod._shutdown_once:
            if mod._shutdown_done:
                return
            mod._shutdown_done = True
        disconnect_mcp_connections_safe()
        mod.shutdown_async_runner(timeout=2.0)

    safe_best_effort(_run, label="async_runner.atexit_shutdown", default=None)
