"""Dedicated asyncio loop for MCP SDK calls from sync Butler code."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Coroutine, TypeVar

T = TypeVar("T")

_loop: asyncio.AbstractEventLoop | None = None
_thread: threading.Thread | None = None
_lock = threading.Lock()


def _ensure_loop() -> asyncio.AbstractEventLoop:
    global _loop, _thread
    with _lock:
        if _loop is not None and _loop.is_running():
            return _loop
        loop = asyncio.new_event_loop()

        def _run() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        _thread = threading.Thread(target=_run, daemon=True, name="butler-mcp-loop")
        _thread.start()
        _loop = loop
        return loop


def run_mcp_async(coro: Coroutine[Any, Any, T], *, timeout: float = 120.0) -> T:
    loop = _ensure_loop()
    future = asyncio.run_coroutine_threadsafe(coro, loop)
    return future.result(timeout=timeout)
