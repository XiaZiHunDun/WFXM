"""WeChat inbound poll + message dispatch (ENG-13 PR-1)."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import urllib.error
import urllib.request
from typing import TYPE_CHECKING, Any, Dict, List, Optional, cast

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


# R8.2: v5 forward — v4 wechat-gateway now forwards incoming iLink messages to
# v5's ``/v1/wechat/inbound`` endpoint and uses v5's reply for the iLink send.
# v4's existing processing is preserved as the fallback when v5 is unreachable.
V5_INBOUND_URL = os.environ.get(
    "V5_INBOUND_URL", "http://127.0.0.1:3000/v1/wechat/inbound",
)
V5_FORWARD_TIMEOUT_SECONDS = float(
    os.environ.get("V5_FORWARD_TIMEOUT", "5.0"),
)
V5_FORWARD_ENABLED = os.environ.get(
    "BUTLER_V5_FORWARD_ENABLED", "1",
) not in ("0", "false", "False", "no", "No", "")


def forward_to_v5(sender_id: str, content: str, message_id: str) -> Optional[str]:
    """Forward a wechat message to v5's ``/v1/wechat/inbound`` endpoint.

    Returns v5's ``reply`` text on success, or ``None`` if v5 is unreachable
    or returned an unusable response. Callers should fall back to v4 processing
    when ``None`` is returned.

    Synchronous (uses :mod:`urllib`); intended to be called via
    :func:`asyncio.loop.run_in_executor` from async contexts.
    """
    payload = json.dumps({
        "apiVersion": "v1",
        "fromUserId": sender_id,
        "content": content,
        "messageId": message_id,
        "projectId": "wechat",
    }, ensure_ascii=False).encode("utf-8")
    try:
        req = urllib.request.Request(
            V5_INBOUND_URL,
            data=payload,
            headers={"content-type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=V5_FORWARD_TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8")
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, TimeoutError) as exc:
        logger.warning(
            "[v5-forward] v5 unreachable from=%s msgid=%s err=%r",
            sender_id, message_id, exc,
        )
        return None
    except Exception as exc:  # noqa: BLE001 — defensive: never let v5 forward crash the adapter
        logger.warning(
            "[v5-forward] unexpected error from=%s msgid=%s err=%r",
            sender_id, message_id, exc,
        )
        return None
    try:
        data = json.loads(raw)
    except (TypeError, ValueError) as exc:
        logger.warning(
            "[v5-forward] v5 returned non-JSON from=%s msgid=%s body=%r err=%r",
            sender_id, message_id, raw[:200], exc,
        )
        return None
    if not isinstance(data, dict):
        logger.warning(
            "[v5-forward] v5 returned non-object from=%s msgid=%s body=%r",
            sender_id, message_id, raw[:200],
        )
        return None
    reply = data.get("reply")
    if not isinstance(reply, str) or not reply:
        logger.warning(
            "[v5-forward] v5 returned no reply field from=%s msgid=%s body=%r",
            sender_id, message_id, raw[:200],
        )
        return None
    return reply


async def _forward_to_v5(sender_id: str, content: str, message_id: str) -> Optional[str]:
    """Async wrapper around :func:`forward_to_v5` — runs urllib in a thread
    so the event loop is not blocked during the (up to ~5s) HTTP call.
    """
    loop = asyncio.get_running_loop()
    return cast(
        Optional[str],
        await loop.run_in_executor(
            None, forward_to_v5, sender_id, content, message_id,
        ),
    )


def poll_backoff_seconds(consecutive_failures: int) -> float:
    from butler.gateway.platforms.wechat_ilink.constants import (
        BACKOFF_DELAY_SECONDS,
        MAX_CONSECUTIVE_FAILURES,
        RETRY_DELAY_SECONDS,
    )

    return float(
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

    # R8.2: v5-forward primary path. When v5 is reachable we send v5's reply
    # via the existing iLink send path and skip v4's full AI processing.
    # When v5 is unreachable (``_forward_to_v5`` returns ``None``) or disabled
    # by ``BUTLER_V5_FORWARD_ENABLED``, we fall back to v4's ``handle_message``
    # so existing behavior is preserved when v5 is down.
    if V5_FORWARD_ENABLED and text:
        v5_reply = await _forward_to_v5(sender_id, text, message_id)
        if v5_reply is not None:
            logger.info(
                "[v5-forward] replying to=%s msgid=%s via v5 reply_len=%d",
                sender_id, message_id, len(v5_reply),
            )
            try:
                send_result = await adapter.send(sender_id, v5_reply)
            except Exception as exc:  # noqa: BLE001 — defensive: iLink send failures must not break the adapter
                logger.warning(
                    "[v5-forward] iLink send raised from=%s msgid=%s err=%r; falling back to v4",
                    sender_id, message_id, exc,
                )
            else:
                if send_result.success:
                    return
                logger.warning(
                    "[v5-forward] iLink send failed from=%s msgid=%s err=%s; falling back to v4",
                    sender_id, message_id, send_result.error,
                )

    await adapter.handle_message(event)


__all__ = [
    "V5_FORWARD_ENABLED",
    "V5_FORWARD_TIMEOUT_SECONDS",
    "V5_INBOUND_URL",
    "dispatch_poll_response",
    "forward_to_v5",
    "handle_poll_exception",
    "poll_backoff_seconds",
    "process_message",
    "process_message_safe",
]
