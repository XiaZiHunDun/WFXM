"""Best-effort helpers for gateway outbound bridge (P0-A / P2-F)."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any, Callable

from butler.core.best_effort import async_safe_best_effort, safe_best_effort

logger = logging.getLogger(__name__)


async def send_adapter_message(
    adapter: Any,
    chat_id: str,
    body: str,
    *,
    label: str,
) -> bool:
    async def _run() -> bool:
        await adapter.send(chat_id, body)
        return True

    return await async_safe_best_effort(_run, label=label, default=False) is True


def schedule_coro_threadsafe(
    loop: asyncio.AbstractEventLoop,
    coro_factory: Callable[[], Coroutine[Any, Any, Any]],
    *,
    label: str,
) -> bool:
    def _run() -> bool:
        asyncio.run_coroutine_threadsafe(coro_factory(), loop)
        return True

    return safe_best_effort(_run, label=label, default=False) is True


async def run_milestone_timer_tick(bridge: Any) -> None:
    async def _run() -> None:
        from butler.gateway.task_milestone import (
            maybe_schedule_task_milestone,
            task_milestone_min_seconds,
        )

        await asyncio.sleep(task_milestone_min_seconds())
        if not bridge._closed and not bridge._final_sent:
            maybe_schedule_task_milestone(bridge)

    await async_safe_best_effort(_run, label="outbound_bridge.milestone_timer", default=None)


async def run_typing_refresh_loop(bridge: Any) -> None:
    async def _run() -> None:
        while not bridge._closed:
            await asyncio.sleep(bridge.typing_refresh_seconds)
            if bridge._closed or bridge._final_sent:
                break
            await bridge._safe_send_typing()

    await async_safe_best_effort(_run, label="outbound_bridge.typing_refresh_loop", default=None)


async def send_progress_ack(
    bridge: Any,
    *,
    text: str,
    elapsed: int,
) -> bool:
    ok = await send_adapter_message(
        bridge.adapter,
        bridge.chat_id,
        text,
        label="outbound_bridge.progress_ack",
    )
    if not ok:
        return False
    bridge._ack_sent = True
    logger.info(
        "Gateway progress ack sent chat_id=%s elapsed=%ds",
        bridge.chat_id,
        elapsed,
    )

    def _schedule_task_milestone() -> None:
        from butler.gateway.task_milestone import maybe_schedule_task_milestone

        maybe_schedule_task_milestone(bridge)

    safe_best_effort(
        _schedule_task_milestone,
        label="outbound_bridge.task_milestone_after_ack",
        default=None,
    )
    return True


__all__ = [
    "run_milestone_timer_tick",
    "run_typing_refresh_loop",
    "schedule_coro_threadsafe",
    "send_adapter_message",
    "send_progress_ack",
]
