"""WeChat outbound send + typing + file upload (ENG-13 PR-2)."""

from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import os
import secrets
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Dict, List, Optional, cast

from butler.env_parse import float_env
from butler.gateway.outbound_prefs import pop_single_bubble_from_metadata
from butler.gateway.platforms.types import SendResult
from butler.gateway.platforms.wechat_ilink import (
    _aes_padded_size,
    _safe_id,
    _split_text_for_wechat_delivery,
)
from butler.gateway.platforms.wechat_ilink.adapter_media import download_remote_media
from butler.gateway.platforms.wechat_ilink.adapter_outbound_ops import (
    backoff_for_rate_limit,
    backoff_for_transport_error,
    ensure_typing_ticket_safe,
    fetch_typing_ticket_safe,
    send_media_loud,
    send_message_loud,
    send_text_chunk_loud,
    send_typing_status_safe,
    unlink_temp_file_safe,
)
from butler.gateway.platforms.wechat_ilink.constants import (
    MEDIA_FILE,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    MEDIA_VOICE,
    TYPING_START,
    TYPING_STOP,
)
from butler.gateway.platforms.wechat_ilink_phases import (
    _build_audio_item,
    _build_file_item,
    _build_image_item,
    _build_video_item,
    _build_voice_item,
    _phase_file_dispatch_message,
    _phase_file_request_upload,
    _phase_send_attachments,
    _phase_send_text_chunks,
)

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def maybe_fetch_typing_ticket(
    adapter: "WeChatAdapter",
    user_id: str,
    context_token: Optional[str],
) -> None:
    await fetch_typing_ticket_safe(adapter, user_id, context_token)


async def ensure_typing_ticket_for_event(adapter: "WeChatAdapter", event: Any) -> None:
    timeout = float_env("BUTLER_GATEWAY_TYPING_FETCH_TIMEOUT_SECONDS", 2)
    await ensure_typing_ticket_safe(adapter, event, timeout=timeout)


def split_text(
    adapter: "WeChatAdapter",
    content: str,
    *,
    metadata: dict[str, Any] | None = None,
) -> List[str]:
    force_single = pop_single_bubble_from_metadata(metadata)
    return cast(
        list[str],
        _split_text_for_wechat_delivery(
        content,
        adapter.MAX_MESSAGE_LENGTH,
        adapter._split_multiline_messages,
        force_single_message=force_single,
        ),
    )


async def send_text_chunk(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    chunk: str,
    context_token: Optional[str],
    client_id: str,
) -> None:
    await send_text_chunk_loud(
        adapter,
        chat_id=chat_id,
        chunk=chunk,
        context_token=context_token,
        client_id=client_id,
    )


async def send_message(
    adapter: "WeChatAdapter",
    chat_id: str,
    content: str,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    del reply_to
    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")
    context_token = adapter._token_store.get(adapter._account_id, chat_id)

    media_files, cleaned_content = adapter.extract_media(content)
    _, image_cleaned = adapter.extract_images(cleaned_content)
    local_files, final_content = adapter.extract_local_files(image_cleaned)

    async def _run_send() -> SendResult:
        await _phase_send_attachments(
            adapter, media_files, local_files, chat_id, metadata,
        )
        last_message_id = await _phase_send_text_chunks(
            adapter, final_content, chat_id, context_token, metadata=metadata,
        )
        return SendResult(success=True, message_id=last_message_id)

    return await send_message_loud(adapter, chat_id, run_send=_run_send)


async def send_typing(
    adapter: "WeChatAdapter",
    chat_id: str,
    metadata: Optional[Dict[str, Any]] = None,
) -> None:
    del metadata
    if not adapter._send_session or not adapter._token:
        return
    await send_typing_status_safe(
        adapter,
        chat_id,
        status=TYPING_START,
        label=f"adapter_outbound.typing_start.{adapter.name}",
    )


async def stop_typing(adapter: "WeChatAdapter", chat_id: str) -> None:
    if not adapter._send_session or not adapter._token:
        return
    await send_typing_status_safe(
        adapter,
        chat_id,
        status=TYPING_STOP,
        label=f"adapter_outbound.typing_stop.{adapter.name}",
    )


async def send_image(
    adapter: "WeChatAdapter",
    chat_id: str,
    image_url: str,
    caption: str,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
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
        if cleanup:
            unlink_temp_file_safe(file_path)


async def send_image_file(
    adapter: "WeChatAdapter",
    chat_id: str,
    image_path: str,
    caption: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
    **kwargs: Any,
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
    **kwargs: Any,
) -> SendResult:
    del file_name, reply_to, metadata, kwargs
    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")

    async def _run_send() -> SendResult:
        message_id = await send_file(adapter, chat_id, file_path, caption or "")
        return SendResult(success=True, message_id=message_id)

    return await send_media_loud(adapter, chat_id, label="send_document", run_send=_run_send)


async def send_video(
    adapter: "WeChatAdapter",
    chat_id: str,
    video_path: str,
    caption: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")

    async def _run_send() -> SendResult:
        message_id = await send_file(adapter, chat_id, video_path, caption or "")
        return SendResult(success=True, message_id=message_id)

    return await send_media_loud(adapter, chat_id, label="send_video", run_send=_run_send)


async def send_voice(
    adapter: "WeChatAdapter",
    chat_id: str,
    audio_path: str,
    caption: Optional[str] = None,
    reply_to: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> SendResult:
    if not adapter._send_session or not adapter._token:
        return SendResult(success=False, error="Not connected")

    fallback_caption = caption or "[voice message as attachment]"

    async def _run_send() -> SendResult:
        message_id = await send_file(
            adapter,
            chat_id,
            audio_path,
            fallback_caption,
            force_file_attachment=True,
        )
        return SendResult(success=True, message_id=message_id)

    return await send_media_loud(adapter, chat_id, label="send_voice", run_send=_run_send)


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
    return cast(Dict[str, Any], item_builder(**item_kwargs))


def outbound_media_builder(
    adapter: "WeChatAdapter",
    path: str,
    force_file_attachment: bool = False,
) -> tuple[int, Callable[..., Dict[str, Any]]]:
    import mimetypes

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
    return cast(
        str,
        await _phase_file_dispatch_message(
        adapter, chat_id=chat_id, media_item=media_item,
        caption=caption, context_token=context_token,
        ),
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
