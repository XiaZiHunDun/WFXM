"""WeChat inbound media download + collect (ENG-13 PR-2)."""

from __future__ import annotations

import asyncio
import base64
import logging
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def collect_media(
    adapter: "WeChatAdapter",
    item: Dict[str, Any],
    media_paths: List[str],
    media_types: List[str],
) -> None:
    from butler.gateway.platforms.wechat_ilink.constants import (
        ITEM_FILE,
        ITEM_IMAGE,
        ITEM_VIDEO,
        ITEM_VOICE,
    )

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
    from butler.gateway.platforms.wechat_ilink import (
        _download_and_decrypt_media,
        _media_reference,
        cache_image_from_bytes,
    )

    media = _media_reference(item, "image_item")
    try:
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
        return cache_image_from_bytes(data, ".jpg")
    except Exception as exc:
        logger.warning("[%s] image download failed: %s", adapter.name, exc)
        return None


async def download_video(adapter: "WeChatAdapter", item: Dict[str, Any]) -> Optional[str]:
    from butler.gateway.platforms.wechat_ilink import (
        _download_and_decrypt_media,
        _media_reference,
        cache_document_from_bytes,
    )

    media = _media_reference(item, "video_item")
    try:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=120.0,
        )
        return cache_document_from_bytes(data, "video.mp4")
    except Exception as exc:
        logger.warning("[%s] video download failed: %s", adapter.name, exc)
        return None


async def download_file(
    adapter: "WeChatAdapter",
    item: Dict[str, Any],
) -> Tuple[Optional[str], str]:
    from butler.gateway.platforms.wechat_ilink import (
        _download_and_decrypt_media,
        _mime_from_filename,
        cache_document_from_bytes,
    )

    file_item = item.get("file_item") or {}
    media = file_item.get("media") or {}
    filename = str(file_item.get("file_name") or "document.bin")
    mime = _mime_from_filename(filename)
    try:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=60.0,
        )
        return cache_document_from_bytes(data, filename), mime
    except Exception as exc:
        logger.warning("[%s] file download failed: %s", adapter.name, exc)
        return None, mime


async def download_voice(adapter: "WeChatAdapter", item: Dict[str, Any]) -> Optional[str]:
    from butler.gateway.platforms.wechat_ilink import (
        _download_and_decrypt_media,
        cache_audio_from_bytes,
    )

    voice_item = item.get("voice_item") or {}
    media = voice_item.get("media") or {}
    if voice_item.get("text"):
        return None
    try:
        data = await _download_and_decrypt_media(
            adapter._poll_session,
            cdn_base_url=adapter._cdn_base_url,
            encrypted_query_param=media.get("encrypt_query_param"),
            aes_key_b64=media.get("aes_key"),
            full_url=media.get("full_url"),
            timeout_seconds=60.0,
        )
        return cache_audio_from_bytes(data, ".silk")
    except Exception as exc:
        logger.warning("[%s] voice download failed: %s", adapter.name, exc)
        return None


async def download_remote_media(adapter: "WeChatAdapter", url: str) -> str:
    from butler.registry.url_safety import is_safe_url

    if not is_safe_url(url):
        raise ValueError(f"Blocked unsafe URL (SSRF protection): {url}")

    assert adapter._send_session is not None

    async def _do_fetch():
        async with adapter._send_session.get(url) as response:
            response.raise_for_status()
            return await response.read()

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
