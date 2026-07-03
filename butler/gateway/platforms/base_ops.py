"""Platform message handler failure helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import async_safe_best_effort
from butler.gateway.platforms.types import SendResult

logger = logging.getLogger(__name__)


async def _send_handler_failure_reply_safe(
    platform: Any,
    *,
    chat_id: str,
    bridge: Any,
    exc: Exception,
) -> None:
    async def _run() -> None:
        if bridge is not None:
            bridge.mark_final_sent()
        from butler.gateway.user_errors import format_gateway_user_error

        await platform.send(chat_id, format_gateway_user_error(exc))

    await async_safe_best_effort(
        _run,
        label="platform_base.handler_failure_reply",
        default=None,
    )


async def handle_platform_message_turn_safe(
    platform: Any,
    *,
    chat_id: str,
    bridge: Any,
    handler_coro: Any,
) -> None:
    try:
        response = await handler_coro
        if response:
            send_metadata: dict[str, Any] = {}
            if bridge is not None and getattr(bridge, "slash_single_bubble", False):
                send_metadata["force_single_bubble"] = True
                bridge.slash_single_bubble = False
            send_result = await platform.send(
                chat_id,
                response,
                metadata=send_metadata or None,
            )
            if isinstance(send_result, SendResult) and not send_result.success:
                logger.error(
                    "[%s] outbound send failed chat=%s: %s",
                    platform.name,
                    chat_id[:24],
                    send_result.error or "unknown",
                )
            elif bridge is not None:
                bridge.mark_final_sent(main_reply_chars=len(response or ""))
                bridge.maybe_notify_turn_complete_after_reply()
    except Exception as exc:
        logger.error("[%s] handler failed: %s", platform.name, exc, exc_info=True)
        await _send_handler_failure_reply_safe(
            platform,
            chat_id=chat_id,
            bridge=bridge,
            exc=exc,
        )
