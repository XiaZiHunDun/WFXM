"""WeChat adapter outbound best-effort helpers (P0-A)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import TYPE_CHECKING, Any, Optional

from butler.core.best_effort import async_safe_best_effort, safe_best_effort
from butler.gateway.platforms.types import SendResult

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def fetch_typing_ticket_safe(
    adapter: "WeChatAdapter",
    user_id: str,
    context_token: Optional[str],
) -> None:
    async def _run() -> None:
        from butler.gateway.platforms.wechat_ilink import _get_config, _safe_id

        response = await _get_config(
            adapter._poll_session,
            base_url=adapter._base_url,
            token=adapter._token,
            user_id=user_id,
            context_token=context_token,
        )
        typing_ticket = str(response.get("typing_ticket") or "")
        if typing_ticket:
            adapter._typing_cache.set(user_id, typing_ticket)

    await async_safe_best_effort(
        _run,
        label=f"adapter_outbound.typing_ticket.{adapter.name}",
        default=None,
    )


async def ensure_typing_ticket_safe(
    adapter: "WeChatAdapter",
    event: Any,
    *,
    timeout: float,
) -> None:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    if not event.source:
        return
    chat_id = event.source.chat_id
    context_token = ""
    raw = event.raw_message if isinstance(event.raw_message, dict) else {}
    context_token = str(raw.get("context_token") or "").strip()
    try:
        await asyncio.wait_for(
            fetch_typing_ticket_safe(adapter, chat_id, context_token or None),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.debug(
            "[%s] typing ticket fetch timed out for %s",
            adapter.name,
            _safe_id(chat_id),
        )


def send_result_from_error(exc: BaseException) -> SendResult:
    return SendResult(success=False, error=str(exc))


async def send_message_loud(
    adapter: "WeChatAdapter",
    chat_id: str,
    *,
    run_send: Any,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    try:
        return await run_send()
    except Exception as exc:
        logger.error("[%s] send failed to=%s: %s", adapter.name, _safe_id(chat_id), exc)
        return send_result_from_error(exc)


async def send_typing_status_safe(
    adapter: "WeChatAdapter",
    chat_id: str,
    *,
    status: int,
    label: str,
) -> None:
    async def _run() -> None:
        from butler.gateway.platforms.wechat_ilink import _send_typing

        typing_ticket = adapter._typing_cache.get(chat_id)
        if not typing_ticket:
            return
        await _send_typing(
            adapter._send_session,
            base_url=adapter._base_url,
            token=adapter._token,
            to_user_id=chat_id,
            typing_ticket=typing_ticket,
            status=status,
        )

    await async_safe_best_effort(_run, label=label, default=None)


async def send_media_loud(
    adapter: "WeChatAdapter",
    chat_id: str,
    *,
    label: str,
    run_send: Any,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    try:
        return await run_send()
    except Exception as exc:
        logger.error("[%s] %s failed to=%s: %s", adapter.name, label, _safe_id(chat_id), exc)
        return send_result_from_error(exc)


async def send_text_chunk_loud(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    chunk: str,
    context_token: Optional[str],
    client_id: str,
) -> None:
    from butler.gateway.platforms.wechat_ilink_phases import (
        WeChatSendState,
        _phase_chunk_attempt,
        _phase_chunk_handle_response,
    )

    last_error: Optional[Exception] = None
    state = WeChatSendState()
    for attempt in range(adapter._send_chunk_retries + 1):
        try:
            resp = await _phase_chunk_attempt(
                adapter, chat_id=chat_id, chunk=chunk,
                context_token=context_token, client_id=client_id,
            )
            action, new_token, err = _phase_chunk_handle_response(
                adapter, resp, chat_id=chat_id,
                context_token=context_token, state=state,
            )
            if action == "ok":
                return
            if action == "retry_without_token":
                context_token = new_token
            elif action == "raise":
                raise err
            elif action == "retry":
                last_error = err
                if attempt >= adapter._send_chunk_retries:
                    break
                from butler.gateway.platforms.wechat_ilink.adapter_outbound import (
                    backoff_for_rate_limit,
                )

                await backoff_for_rate_limit(adapter, chat_id, attempt)
        except Exception as exc:
            last_error = exc
            if attempt >= adapter._send_chunk_retries:
                break
            from butler.gateway.platforms.wechat_ilink.adapter_outbound import (
                backoff_for_transport_error,
            )

            await backoff_for_transport_error(adapter, chat_id, attempt, exc)
    assert last_error is not None
    raise last_error


def unlink_temp_file_safe(file_path: str) -> None:
    def _run() -> None:
        if file_path and os.path.exists(file_path):
            os.unlink(file_path)

    safe_best_effort(_run, label="adapter_outbound.unlink_temp", default=None)
