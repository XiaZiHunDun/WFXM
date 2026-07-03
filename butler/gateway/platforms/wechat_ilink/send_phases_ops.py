"""WeChat send phase attachment delivery best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import async_safe_best_effort

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

_AUDIO_EXTS = {".ogg", ".opus", ".mp3", ".wav", ".m4a", ".flac"}
_VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"}
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}


async def deliver_attachment_safe(
    adapter: "WeChatAdapter",
    *,
    path: str,
    is_voice: bool,
    chat_id: str,
    metadata: dict[str, Any] | None,
) -> None:
    async def _run() -> None:
        ext = Path(path).suffix.lower()
        if is_voice or ext in _AUDIO_EXTS:
            await adapter.send_voice(chat_id=chat_id, audio_path=path, metadata=metadata)
        elif ext in _VIDEO_EXTS:
            await adapter.send_video(chat_id=chat_id, video_path=path, metadata=metadata)
        elif ext in _IMAGE_EXTS:
            await adapter.send_image_file(chat_id=chat_id, image_path=path, metadata=metadata)
        else:
            await adapter.send_document(chat_id=chat_id, file_path=path, metadata=metadata)

    await async_safe_best_effort(
        _run,
        label=f"send_phases.deliver.{adapter.name}",
        default=None,
    )
