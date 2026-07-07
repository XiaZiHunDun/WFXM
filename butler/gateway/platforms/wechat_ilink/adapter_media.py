"""WeChat inbound media download + collect (ENG-13 PR-2)."""

from __future__ import annotations

import asyncio
import base64
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

from butler.gateway.platforms.wechat_ilink.constants import (
    ITEM_FILE,
    ITEM_IMAGE,
    ITEM_VIDEO,
    ITEM_VOICE,
)
from butler.gateway.platforms.wechat_ilink import (
    _download_and_decrypt_media,
    _media_reference,
    cache_image_from_bytes,
    cache_document_from_bytes,
    _mime_from_filename,
    cache_audio_from_bytes,
)
from butler.gateway.platforms.wechat_ilink.adapter_media_ops import (
    download_media_loud,
    download_file_loud,
)
from butler.registry.url_safety import is_safe_url

logger = logging.getLogger(__name__)


async def collect_media(
    adapter: "WeChatAdapter",
    item: Dict[str, Any],
    media_paths: List[str],
    media_types: List[str],
) -> None:

    item_type = item.get("type")
    if item_type == ITEM_IMAGE:
        path = await adapter._download_image(item)
        if path:
            media_paths.append(path)
            media_types.append("image/jpeg")
    elif item_type == ITEM_VIDEO:
        path = await adapter._download_video(item)
        if path:
            media_paths.append(path)
            media_types.append("video/mp4")
    elif item_type == ITEM_FILE:
        path, mime = await adapter._download_file(item)
        if path:
            media_paths.append(path)
            media_types.append(mime)
    elif item_type == ITEM_VOICE:
        voice_path = await adapter._download_voice(item)
        if voice_path:
            media_paths.append(voice_path)
            media_types.append("audio/silk")


async def download_image(adapter: "WeChatAdapter", item: Dict[str, Any]) -> Optional[str]:

    media = _media_reference(item, "image_item")

    async def _run() -> Optional[str]:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=(item.get("image_item") or {}).get("aeskey")
            and base64.b64encode(bytes.fromhex(str((item.get("image_item") or {}).get("aeskey")))).decode("ascii")
            or media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=30.0,
        )
        return cast(Optional[str], cache_image_from_bytes(data, ".jpg"))

    return cast(
        Optional[str],
        await download_media_loud(adapter, label="image download", run_download=_run),
    )


async def download_video(adapter: "WeChatAdapter", item: Dict[str, Any]) -> Optional[str]:

    media = _media_reference(item, "video_item")

    async def _run() -> Optional[str]:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=120.0,
        )
        return cast(Optional[str], cache_document_from_bytes(data, "video.mp4"))

    return cast(
        Optional[str],
        await download_media_loud(adapter, label="video download", run_download=_run),
    )


async def download_file(
    adapter: "WeChatAdapter",
    item: Dict[str, Any],
) -> Tuple[Optional[str], str]:

    file_item = item.get("file_item") or {}
    media = file_item.get("media") or {}
    filename = str(file_item.get("file_name") or "document.bin")
    mime = _mime_from_filename(filename)

    async def _run() -> Tuple[Optional[str], str]:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=60.0,
        )
        return cast(Tuple[Optional[str], str], (cache_document_from_bytes(data, filename), mime))

    return cast(
        Tuple[Optional[str], str],
        await download_file_loud(
            adapter,
            run_download=_run,
            default_mime=mime,
        ),
    )


async def download_voice(adapter: "WeChatAdapter", item: Dict[str, Any]) -> Optional[str]:

    voice_item = item.get("voice_item") or {}
    media = voice_item.get("media") or {}
    if voice_item.get("text"):
        return None

    async def _run() -> Optional[str]:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=60.0,
        )
        return cast(Optional[str], cache_audio_from_bytes(data, ".silk"))

    return cast(
        Optional[str],
        await download_media_loud(adapter, label="voice download", run_download=_run),
    )


async def download_remote_media(adapter: "WeChatAdapter", url: str) -> str:

    if not is_safe_url(url):
        raise ValueError(f"Blocked unsafe URL (SSRF protection): {url}")

    send_session = adapter._send_session
    assert send_session is not None

    async def _do_fetch() -> bytes:
        async with send_session.get(url) as response:
            response.raise_for_status()
            return cast(bytes, await response.read())

    data = await asyncio.wait_for(_do_fetch(), timeout=30)
    suffix = Path(url.split("?", 1)[0]).suffix or ".bin"
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        handle.write(data)
        return handle.name


__all__ = [
    "collect_media",
    "download_file",
    "download_image",
    "download_remote_media",
    "download_video",
    "download_voice",
]
