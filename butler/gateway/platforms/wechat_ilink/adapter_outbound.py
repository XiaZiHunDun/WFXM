"""WeChat outbound send + typing + file upload (ENG-13 PR-2)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from butler.env_parse import float_env
from butler.gateway.platforms.types import SendResult

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def maybe_fetch_typing_ticket(
    adapter: "WeChatAdapter",
    user_id: str,
    context_token: Optional[str],
) -> None:
    from butler.gateway.platforms.wechat_ilink import _get_config, _safe_id

    if not adapter._poll_session or not adapter._token:
        return
    if adapter._typing_cache.get(user_id):
        return
    try:
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
    except Exception as exc:
        logger.debug("[%s] getConfig failed for %s: %s", adapter.name, _safe_id(user_id), exc)


async def ensure_typing_ticket_for_event(adapter: "WeChatAdapter", event: Any) -> None:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    if not event.source:
        return
    chat_id = event.source.chat_id
    timeout = float_env("BUTLER_GATEWAY_TYPING_FETCH_TIMEOUT_SECONDS", 2)
    context_token = ""
    raw = event.raw_message if isinstance(event.raw_message, dict) else {}
    context_token = str(raw.get("context_token") or "").strip()
    try:
        await asyncio.wait_for(
            maybe_fetch_typing_ticket(adapter, chat_id, context_token or None),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        logger.debug("[%s] typing ticket fetch timed out for %s", adapter.name, _safe_id(chat_id))


def split_text(
    adapter: "WeChatAdapter",
    content: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> List[str]:
    from butler.gateway.outbound_prefs import pop_single_bubble_from_metadata
    from butler.gateway.platforms.wechat_ilink import _split_text_for_wechat_delivery

    force_single = pop_single_bubble_from_metadata(metadata)
    return _split_text_for_wechat_delivery(
        content,
        adapter.MAX_MESSAGE_LENGTH,
        adapter._split_multiline_messages,
        force_single_message=force_single,
    )


async def backoff_for_rate_limit(adapter: "WeChatAdapter", chat_id: str, attempt: int) -> None:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    cap = 90.0
    try:
        cap = max(10.0, float_env("BUTLER_WECHAT_RATE_LIMIT_BACKOFF_MAX", 90))
    except ValueError:
        cap = 90.0
    wait = min(cap, adapter._send_chunk_retry_delay_seconds * (3 ** attempt))
    logger.warning(
        "[%s] rate limited for %s; backing off %.1fs before retry",
        adapter.name, _safe_id(chat_id), wait,
    )
    await asyncio.sleep(wait)


async def backoff_for_transport_error(
    adapter: "WeChatAdapter",
    chat_id: str,
    attempt: int,
    exc: Exception,
) -> None:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    wait = adapter._send_chunk_retry_delay_seconds * (attempt + 1)
    logger.warning(
        "[%s] send chunk failed to=%s attempt=%d/%d, retrying in %.2fs: %s",
        adapter.name, _safe_id(chat_id),
        attempt + 1, adapter._send_chunk_retries + 1, wait, exc,
    )
    if wait > 0:
        await asyncio.sleep(wait)


async def send_text_chunk(
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
                await backoff_for_rate_limit(adapter, chat_id, attempt)
        except Exception as exc:
            last_error = exc
            if attempt >= adapter._send_chunk_retries:
                break
            await backoff_for_transport_error(adapter, chat_id, attempt, exc)
    assert last_error is not None
    raise last_error


async def send_message(
    adapter: "WeChatAdapter",
    chat_id: str,
    content: str,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink import _safe_id
    from butler.gateway.platforms.wechat_ilink_phases import (
        _phase_send_attachments,
        _phase_send_text_chunks,
    )

    del reply_to
    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")
    context_token = adapter._token_store.get(adapter._account_id, chat_id)

    media_files, cleaned_content = adapter.extract_media(content)
    _, image_cleaned = adapter.extract_images(cleaned_content)
    local_files, final_content = adapter.extract_local_files(image_cleaned)

    try:
        await _phase_send_attachments(
            adapter, media_files, local_files, chat_id, metadata,
        )
        last_message_id = await _phase_send_text_chunks(
            adapter, final_content, chat_id, context_token, metadata=metadata,
        )
        return SendResult(success=True, message_id=last_message_id)
    except Exception as exc:
        logger.error("[%s] send failed to=%s: %s", adapter.name, _safe_id(chat_id), exc)
        return SendResult(success=False, error=str(exc))


async def send_typing(
    adapter: "WeChatAdapter",
    chat_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    from butler.gateway.platforms.wechat_ilink import _safe_id, _send_typing
    from butler.gateway.platforms.wechat_ilink.constants import TYPING_START

    del metadata
    if not adapter._send_session or not adapter._token:
        return
    typing_ticket = adapter._typing_cache.get(chat_id)
    if not typing_ticket:
        return
    try:
        await _send_typing(
            adapter._send_session,
            base_url=adapter._base_url,
            token=adapter._token,
            to_user_id=chat_id,
            typing_ticket=typing_ticket,
            status=TYPING_START,
        )
    except Exception as exc:
        logger.debug("[%s] typing start failed for %s: %s", adapter.name, _safe_id(chat_id), exc)


async def stop_typing(adapter: "WeChatAdapter", chat_id: str) -> None:
    from butler.gateway.platforms.wechat_ilink import _safe_id, _send_typing
    from butler.gateway.platforms.wechat_ilink.constants import TYPING_STOP

    if not adapter._send_session or not adapter._token:
        return
    typing_ticket = adapter._typing_cache.get(chat_id)
    if not typing_ticket:
        return
    try:
        await _send_typing(
            adapter._send_session,
            base_url=adapter._base_url,
            token=adapter._token,
            to_user_id=chat_id,
            typing_ticket=typing_ticket,
            status=TYPING_STOP,
        )
    except Exception as exc:
        logger.debug("[%s] typing stop failed for %s: %s", adapter.name, _safe_id(chat_id), exc)


async def send_image(
    adapter: "WeChatAdapter",
    chat_id: str,
    image_url: str,
    caption: str,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink.adapter_media import download_remote_media

    if image_url.startswith(("http://", "https://")):
        file_path = await download_remote_media(adapter, image_url)
        cleanup = True
    else:
        file_path = image_url.replace("file://", "")
        if not os.path.isabs(file_path):
            file_path = os.path.abspath(file_path)
        cleanup = False
    try:
        return await send_document(adapter, chat_id, file_path, caption=caption, metadata=metadata)
    finally:
        if cleanup and file_path and os.path.exists(file_path):
            try:
                os.unlink(file_path)
            except OSError:
                pass


async def send_image_file(
    adapter: "WeChatAdapter",
    chat_id: str,
    image_path: str,
    caption: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> SendResult:
    del reply_to, kwargs
    return await send_document(
        adapter,
        chat_id=chat_id,
        file_path=image_path,
        caption=caption,
        metadata=metadata,
    )


async def send_document(
    adapter: "WeChatAdapter",
    chat_id: str,
    file_path: str,
    caption: Optional[str] = None,
    file_name: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    del file_name, reply_to, metadata, kwargs
    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")
    try:
        message_id = await send_file(adapter, chat_id, file_path, caption or "")
        return SendResult(success=True, message_id=message_id)
    except Exception as exc:
        logger.error("[%s] send_document failed to=%s: %s", adapter.name, _safe_id(chat_id), exc)
        return SendResult(success=False, error=str(exc))


async def send_video(
    adapter: "WeChatAdapter",
    chat_id: str,
    video_path: str,
    caption: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")
    try:
        message_id = await send_file(adapter, chat_id, video_path, caption or "")
        return SendResult(success=True, message_id=message_id)
    except Exception as exc:
        logger.error("[%s] send_video failed to=%s: %s", adapter.name, _safe_id(chat_id), exc)
        return SendResult(success=False, error=str(exc))


async def send_voice(
    adapter: "WeChatAdapter",
    chat_id: str,
    audio_path: str,
    caption: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    from butler.gateway.platforms.wechat_ilink import _safe_id

    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")

    fallback_caption = caption or "[voice message as attachment]"
    try:
        message_id = await send_file(
            adapter,
            chat_id,
            audio_path,
            fallback_caption,
            force_file_attachment=True,
        )
        return SendResult(success=True, message_id=message_id)
    except Exception as exc:
        logger.error("[%s] send_voice failed to=%s: %s", adapter.name, _safe_id(chat_id), exc)
        return SendResult(success=False, error=str(exc))


def build_outbound_media_item(
    adapter: "WeChatAdapter",
    path: str,
    media_type: int,
    item_builder: Any,
    *,
    encrypted_query_param: str,
    aes_key: bytes,
    ciphertext_size: int,
    plaintext_size: int,
    rawfilemd5: str,
) -> Dict[str, Any]:
    from butler.gateway.platforms.wechat_ilink.constants import MEDIA_VOICE

    aes_key_for_api = base64.b64encode(aes_key.hex().encode("ascii")).decode("ascii")
    item_kwargs: Dict[str, Any] = {
        "encrypt_query_param": encrypted_query_param,
        "aes_key_for_api": aes_key_for_api,
        "ciphertext_size": ciphertext_size,
        "plaintext_size": plaintext_size,
        "filename": Path(path).name,
        "rawfilemd5": rawfilemd5,
    }
    if media_type == MEDIA_VOICE and path.endswith(".silk"):
        item_kwargs["encode_type"] = 6
        item_kwargs["sample_rate"] = 24000
        item_kwargs["bits_per_sample"] = 16
    return item_builder(**item_kwargs)


def outbound_media_builder(adapter: "WeChatAdapter", path: str, force_file_attachment: bool = False):
    import mimetypes

    from butler.gateway.platforms.wechat_ilink.constants import (
        MEDIA_FILE,
        MEDIA_IMAGE,
        MEDIA_VIDEO,
        MEDIA_VOICE,
    )
    from butler.gateway.platforms.wechat_ilink_phases import (
        _build_audio_item,
        _build_file_item,
        _build_image_item,
        _build_video_item,
        _build_voice_item,
    )

    mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
    if mime.startswith("image/"):
        return MEDIA_IMAGE, _build_image_item
    if mime.startswith("video/"):
        return MEDIA_VIDEO, _build_video_item
    if path.endswith(".silk") and not force_file_attachment:
        return MEDIA_VOICE, _build_voice_item
    if mime.startswith("audio/"):
        return MEDIA_FILE, _build_audio_item
    return MEDIA_FILE, _build_file_item


async def send_file(
    adapter: "WeChatAdapter",
    chat_id: str,
    path: str,
    caption: str,
    force_file_attachment: bool = False,
) -> str:
    from butler.gateway.platforms.wechat_ilink import _aes_padded_size
    from butler.gateway.platforms.wechat_ilink_phases import (
        _phase_file_dispatch_message,
        _phase_file_request_upload,
    )

    assert adapter._send_session is not None and adapter._token is not None
    plaintext = Path(path).read_bytes()
    media_type, item_builder = outbound_media_builder(
        adapter, path, force_file_attachment=force_file_attachment,
    )
    filekey = secrets.token_hex(16)
    aes_key = secrets.token_bytes(16)
    rawsize = len(plaintext)
    rawfilemd5 = hashlib.md5(plaintext).hexdigest()
    _upload_url, encrypted_query_param, ciphertext = await _phase_file_request_upload(
        adapter, chat_id=chat_id, media_type=media_type,
        filekey=filekey, aes_key=aes_key, plaintext=plaintext,
        rawsize=rawsize, rawfilemd5=rawfilemd5,
        filesize=_aes_padded_size(rawsize),
    )
    context_token = adapter._token_store.get(adapter._account_id, chat_id)
    media_item = build_outbound_media_item(
        adapter, path, media_type, item_builder,
        encrypted_query_param=encrypted_query_param,
        aes_key=aes_key,
        ciphertext_size=len(ciphertext),
        plaintext_size=rawsize,
        rawfilemd5=rawfilemd5,
    )
    return await _phase_file_dispatch_message(
        adapter, chat_id=chat_id, media_item=media_item,
        caption=caption, context_token=context_token,
    )


__all__ = [
    "backoff_for_rate_limit",
    "backoff_for_transport_error",
    "build_outbound_media_item",
    "ensure_typing_ticket_for_event",
    "maybe_fetch_typing_ticket",
    "outbound_media_builder",
    "send_document",
    "send_file",
    "send_image",
    "send_image_file",
    "send_message",
    "send_text_chunk",
    "send_typing",
    "send_video",
    "send_voice",
    "split_text",
    "stop_typing",
]
