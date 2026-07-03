"""WeChat inbound dispatch best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable, Dict, TYPE_CHECKING

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def process_inbound_message_safe(
    adapter: "WeChatAdapter",
    message: Dict[str, Any],
    *,
    process_fn: Callable[["WeChatAdapter", Dict[str, Any]], Awaitable[None]],
) -> None:
    try:
        await process_fn(adapter, message)
    except Exception as exc:
        from butler.gateway.platforms.wechat_ilink import _safe_id

        logger.error(
            "[%s] unhandled inbound error from=%s: %s",
            adapter.name,
            _safe_id(message.get("from_user_id")),
            exc,
            exc_info=True,
        )
