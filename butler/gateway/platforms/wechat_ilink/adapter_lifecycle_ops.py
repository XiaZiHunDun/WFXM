"""WeChat adapter lifecycle helpers (P0-A)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Awaitable, Callable

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def connect_loud(
    adapter: "WeChatAdapter",
    *,
    run_connect: Callable[[], bool],
    rollback_disconnect: Callable[[], Awaitable[None]],
) -> bool:
    try:
        return run_connect()
    except Exception as exc:
        logger.warning("[%s] connect failed: %s", adapter.name, exc)
        if not adapter.is_connected:
            await disconnect_rollback_safe(adapter, rollback_disconnect)
        adapter._set_fatal_error(
            "wechat_connect_failed",
            str(exc)[:300],
            retryable=True,
        )
        return False


async def disconnect_rollback_safe(
    adapter: "WeChatAdapter",
    rollback_disconnect: Callable[[], Awaitable[None]],
) -> None:
    try:
        await rollback_disconnect()
    except Exception as exc:
        logger.debug("[%s] connect rollback disconnect: %s", adapter.name, exc)


async def poll_iteration_loud(
    adapter: "WeChatAdapter",
    *,
    run_iteration: Callable[[], Awaitable[Any]],
    consecutive_failures: int,
) -> Any:
    try:
        return await run_iteration()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return await adapter._handle_poll_exception(exc, consecutive_failures)
