"""Effect-style timeout utilities."""

from __future__ import annotations

import asyncio
import signal
import threading
import time
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def with_timeout(
    seconds: float,
    *,
    default: Any = None,
    raise_on_timeout: bool = False,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """Decorate a function to apply timeout."""

    def decorator(fn: Callable[..., T]) -> Callable[..., T]:
        def wrapper(*args, **kwargs) -> T | Any:
            result: list[T | Any] = [default]
            event = threading.Event()

            def target() -> None:
                try:
                    result[0] = fn(*args, **kwargs)
                finally:
                    event.set()

            thread = threading.Thread(target=target)
            thread.start()
            if not event.wait(timeout=seconds):
                if raise_on_timeout:
                    raise TimeoutError(f"Timeout after {seconds}s")
                return default
            thread.join()
            return result[0]

        return wrapper

    return decorator


async def async_with_timeout(
    awaitable,
    seconds: float,
    *,
    default: Any = None,
    raise_on_timeout: bool = False,
):
    """Apply timeout to an async awaitable."""
    try:
        return await asyncio.wait_for(awaitable, timeout=seconds)
    except asyncio.TimeoutError:
        if raise_on_timeout:
            raise TimeoutError(f"Timeout after {seconds}s")
        return default


def timeout_with_default(
    fn: Callable[..., T],
    seconds: float,
    default: Any = None,
) -> T | Any:
    """Run a function with timeout, returning default on timeout."""
    return with_timeout(seconds, default=default)(fn)()