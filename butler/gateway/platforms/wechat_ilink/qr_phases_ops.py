"""WeChat QR login phase best-effort helpers (P0-A)."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


async def fetch_qr_response_safe(
    fetch: Callable[[], Any],
    *,
    label: str,
) -> Any | None:
    try:
        return await fetch()
    except Exception as exc:
        logger.error("wechat: %s: %s", label, exc)
        return None


def render_qr_ascii_safe(qr_scan_data: str) -> None:
    try:
        import qrcode  # type: ignore[import-untyped]

        qr = qrcode.QRCode()
        qr.add_data(qr_scan_data)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception as exc:
        print(f"（终端二维码渲染失败: {exc}，请直接打开上面的二维码链接）")


async def poll_qr_api_safe(fetch: Callable[[], Any]) -> Any | None:
    try:
        return await fetch()
    except asyncio.TimeoutError:
        return None
    except Exception as exc:
        logger.warning("wechat: QR poll error: %s", exc)
        return None
