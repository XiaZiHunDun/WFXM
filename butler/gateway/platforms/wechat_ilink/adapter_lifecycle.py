"""WeChat adapter connect / disconnect / poll loop (ENG-13 PR-3)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


def schedule_typing_ticket_bg(
    adapter: "WeChatAdapter",
    user_id: str,
    context_token: Optional[str],
) -> None:
    """Fire-and-forget typing-ticket fetch; task retained for disconnect cancel."""
    task = asyncio.create_task(
        adapter._maybe_fetch_typing_ticket(user_id, context_token)
    )
    adapter._bg_typing_tasks.add(task)
    task.add_done_callback(adapter._bg_typing_tasks.discard)


async def connect(adapter: "WeChatAdapter") -> bool:
    from butler.gateway.platforms.wechat_ilink_phases import (
        _phase_connect_open_sessions,
        _phase_connect_validate,
    )

    if not _phase_connect_validate(adapter):
        return False
    try:
        _phase_connect_open_sessions(adapter)
        return adapter.is_connected
    except Exception as exc:
        logger.warning("[%s] connect failed: %s", adapter.name, exc)
        if not adapter.is_connected:
            try:
                await disconnect(adapter)
            except Exception as d_exc:
                logger.debug("[%s] connect rollback disconnect: %s", adapter.name, d_exc)
        adapter._set_fatal_error(
            "wechat_connect_failed",
            str(exc)[:300],
            retryable=True,
        )
        return False


async def disconnect(adapter: "WeChatAdapter") -> None:
    from butler.gateway.platforms.wechat_ilink._compat import _ADAPTER_REGISTRY

    _ADAPTER_REGISTRY.unregister(adapter._token)
    adapter._running = False
    if adapter._poll_task and not adapter._poll_task.done():
        adapter._poll_task.cancel()
        try:
            await adapter._poll_task
        except asyncio.CancelledError:
            pass
    adapter._poll_task = None
    pending_bg = [t for t in adapter._bg_typing_tasks if not t.done()]
    for t in pending_bg:
        t.cancel()
    if pending_bg:
        await asyncio.gather(*pending_bg, return_exceptions=True)
    adapter._bg_typing_tasks.clear()
    if adapter._poll_session and not adapter._poll_session.closed:
        await adapter._poll_session.close()
    adapter._poll_session = None
    if adapter._send_session and not adapter._send_session.closed:
        await adapter._send_session.close()
    adapter._send_session = None
    adapter._release_platform_lock()
    adapter._mark_disconnected()
    logger.info("[%s] Disconnected", adapter.name)


async def poll_loop(adapter: "WeChatAdapter") -> None:
    from butler.gateway.platforms.wechat_ilink._compat import (
        LONG_POLL_TIMEOUT_MS,
        _get_updates,
        _load_sync_buf,
    )
    from butler.gateway.platforms.wechat_ilink_phases import _phase_poll_handle_response

    assert adapter._poll_session is not None
    sync_buf = _load_sync_buf(adapter._data_home, adapter._account_id)
    timeout_ms = LONG_POLL_TIMEOUT_MS
    consecutive_failures = 0

    while adapter._running:
        try:
            response = await _get_updates(
                adapter._poll_session,
                base_url=adapter._base_url,
                token=adapter._token,
                sync_buf=sync_buf,
                timeout_ms=timeout_ms,
            )
            suggested_timeout = response.get("longpolling_timeout_ms")
            if isinstance(suggested_timeout, int) and suggested_timeout > 0:
                timeout_ms = suggested_timeout
            new_sync_buf = str(response.get("get_updates_buf") or "").strip()
            if new_sync_buf:
                sync_buf = new_sync_buf
            consecutive_failures = await adapter._dispatch_poll_response(
                response, consecutive_failures, _phase_poll_handle_response,
            )
        except asyncio.CancelledError:
            break
        except Exception as exc:
            consecutive_failures = await adapter._handle_poll_exception(
                exc, consecutive_failures,
            )


__all__ = ["connect", "disconnect", "poll_loop", "schedule_typing_ticket_bg"]
