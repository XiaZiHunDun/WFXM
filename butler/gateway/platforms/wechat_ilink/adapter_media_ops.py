"""WeChat adapter media download helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Callable, Optional, Tuple

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter

logger = logging.getLogger(__name__)


async def download_media_loud(
    adapter: "WeChatAdapter",
    *,
    label: str,
    run_download: Callable[[], Any],
    default: Any = None,
) -> Any:
    try:
        return await run_download()
    except Exception as exc:
        logger.warning("[%s] %s failed: %s", adapter.name, label, exc)
        return default


async def download_file_loud(
    adapter: "WeChatAdapter",
    *,
    run_download: Callable[[], Tuple[Optional[str], str]],
    default_mime: str,
) -> Tuple[Optional[str], str]:
    result = await download_media_loud(
        adapter,
        label="file download",
        run_download=run_download,
        default=(None, default_mime),
    )
    if isinstance(result, tuple) and len(result) == 2:
        return result[0], str(result[1])
    return None, default_mime
