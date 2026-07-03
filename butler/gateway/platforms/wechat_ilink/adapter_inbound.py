"""WeChat inbound poll + message dispatch (ENG-13 PR-1)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


def poll_backoff_seconds(consecutive_failures: int) -> float:
    from butler.gateway.platforms.wechat_ilink.constants import (
        BACKOFF_DELAY_SECONDS,
        MAX_CONSECUTIVE_FAILURES,
        RETRY_DELAY_SECONDS,
    )

    return (
        BACKOFF_DELAY_SECONDS
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES
        else RETRY_DELAY_SECONDS
    )


async def dispatch_poll_response(
    adapter: "WeChatAdapter",
    response: Dict[str, Any],
    consecutive_failures: int,
    handle_response: Any,
) -> int:
    """Dispatch one poll response. Returns the updated failure counter."""
    from butler.gateway.platforms.wechat_ilink.constants import MAX_CONSECUTIVE_FAILURES

    signal, messages = handle_response(adapter, response)
    if signal == "session_expired":
        await asyncio.sleep(600)
        return 0
    ret = response.get("ret", 0)
    errcode = response.get("errcode", 0)
    if ret not in (0, None) or errcode not in (0, None):
        consecutive_failures += 1
        logger.warning(
            "[%s] getUpdates failed ret=%s errcode=%s errmsg=%s (%d/%d)",
            adapter.name, ret, errcode, response.get("errmsg", ""),
            consecutive_failures, MAX_CONSECUTIVE_FAILURES,
        )
        await asyncio.sleep(poll_backoff_seconds(consecutive_failures))
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            return 0
        return consecutive_failures
    for message in messages:
        await process_message_safe(adapter, message)
    return 0


async def handle_poll_exception(
    adapter: "WeChatAdapter",
    exc: Exception,
    consecutive_failures: int,
) -> int:
    """Outer-exception backoff branch for ``_poll_loop``."""
    from butler.gateway.platforms.wechat_ilink.constants import MAX_CONSECUTIVE_FAILURES

    consecutive_failures += 1
    logger.error(
        "[%s] poll error (%d/%d): %s",
        adapter.name, consecutive_failures, MAX_CONSECUTIVE_FAILURES, exc,
    )
    await asyncio.sleep(poll_backoff_seconds(consecutive_failures))
    if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        return 0
    return consecutive_failures


async def process_message_safe(adapter: "WeChatAdapter", message: Dict[str, Any]) -> None:
    from butler.gateway.platforms.wechat_ilink.adapter_inbound_ops import (
        process_inbound_message_safe,
    )

    await process_inbound_message_safe(adapter, message, process_fn=process_message)


async def process_message(adapter: "WeChatAdapter", message: Dict[str, Any]) -> None:
    from butler.gateway.platforms.wechat_ilink import (
        _extract_text,
        _guess_chat_type,
    )
    from butler.gateway.platforms.wechat_ilink.phases import (
        _phase_inbound_build_event,
        _phase_inbound_chat_policy,
        _phase_inbound_dedup,
    )

    assert adapter._poll_session is not None
    sender_id = str(message.get("from_user_id") or "").strip()
    if not sender_id:
        return
    if sender_id == adapter._account_id:
        return

    message_id = str(message.get("message_id") or "").strip()
    item_list = message.get("item_list") or []
    text = _extract_text(item_list)

    if not _phase_inbound_dedup(adapter, message, sender_id, text):
        return

    chat_type, effective_chat_id = _guess_chat_type(message, adapter._account_id)
    if not _phase_inbound_chat_policy(adapter, chat_type, effective_chat_id, sender_id):
        return

    context_token = str(message.get("context_token") or "").strip()
    if context_token:
        adapter._token_store.set(adapter._account_id, sender_id, context_token)
    adapter._schedule_typing_ticket_bg(sender_id, context_token or None)

    media_paths: List[str] = []
    media_types: List[str] = []
    for item in item_list:
        await adapter._collect_media(item, media_paths, media_types)
        ref_message = item.get("ref_msg") or {}
        ref_item = ref_message.get("message_item")
        if isinstance(ref_item, dict):
            await adapter._collect_media(ref_item, media_paths, media_types)

    if not text and not media_paths:
        return

    event = _phase_inbound_build_event(
        adapter, message, sender_id, text, media_paths, media_types,
        effective_chat_id, chat_type, message_id,
    )
    await adapter.handle_message(event)


__all__ = [
    "dispatch_poll_response",
    "handle_poll_exception",
    "poll_backoff_seconds",
    "process_message",
    "process_message_safe",
]
