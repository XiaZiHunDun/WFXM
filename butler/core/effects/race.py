"""Effect-style race utilities."""

from __future__ import annotations

import asyncio
import threading
from typing import Any, Callable, TypeVar

from butler.core.effects.result import Result, Ok, Err

T = TypeVar("T")


def race(
    *fns: Callable[..., T],
    timeout: float | None = None,
) -> Result[tuple[T, int], RuntimeError]:
    """Run multiple functions concurrently and return the first result.

    Returns:
        Ok((result, index)) — the first result and its position in the input list.
        Err(RuntimeError) — if all functions failed or timed out.
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
            return Ok(result)
    return Err(RuntimeError("All functions failed or timed out"))


async def async_race(
    *awaitables,
    timeout: float | None = None,
) -> Result[Any, RuntimeError]:
    """Run multiple awaitables concurrently and return the first result.

    Returns:
        Ok(result) — the first completed result.
        Err(RuntimeError) — if all awaitables timed out.
    """
    tasks = [asyncio.create_task(a) for a in awaitables]
    done, pending = await asyncio.wait(
        tasks,
        return_when=asyncio.FIRST_COMPLETED,
        timeout=timeout,
    )
    for task in pending:
        task.cancel()
    if done:
        return Ok(await done.pop())
    return Err(RuntimeError("All awaitables timed out"))