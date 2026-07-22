"""Effect-style race utilities."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, TypeVar

T = TypeVar("T")


def race(
    *fns: Callable[..., T],
    timeout: float | None = None,
) -> tuple[T, int]:
    """Run multiple functions concurrently and return the first result.

    Returns:
        (result, index) — the first result and its position in the input list.
    """
    results: list[tuple[T, int] | None] = [None] * len(fns)
    done = threading.Event()

    def target(index: int, fn: Callable[..., T]) -> None:
        try:
            results[index] = (fn(), index)
        finally:
            done.set()

    threads = []
    for i, fn in enumerate(fns):
        t = threading.Thread(target=target, args=(i, fn))
        t.start()
        threads.append(t)

    done.wait(timeout=timeout)
    for t in threads:
        t.join(timeout=0.1)

    for result in results:
        if result is not None:
            return result
    raise RuntimeError("All functions failed or timed out")


async def async_race(
    *awaitables,
    timeout: float | None = None,
):
    """Run multiple awaitables concurrently and return the first result."""
    tasks = [asyncio.create_task(a) for a in awaitables]
    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED,
        timeout=timeout,
    )
    for task in pending:
        task.cancel()
    if done:
        return await done.pop()
    raise RuntimeError("All awaitables timed out")