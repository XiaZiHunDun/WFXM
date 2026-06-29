"""Interactive iLink QR login orchestrator (ENG-13 PR-3)."""

from __future__ import annotations

import asyncio
import time
from typing import Dict, Optional

from butler.gateway.platforms.wechat_ilink._compat import (
    AIOHTTP_AVAILABLE,
    ILINK_BASE_URL,
    _make_ssl_connector,
    aiohttp,
)


async def qr_login(
    data_home: str,
    *,
    bot_type: str = "3",
    timeout_seconds: int = 480,
) -> Optional[Dict[str, str]]:
    """
    Run the interactive iLink QR login flow.

    Returns a credential dict on success, or ``None`` if login fails or times out.
    """
    from butler.gateway.platforms.wechat_ilink_phases import (
        QrLoginState,
        _phase_qr_finalize,
        _phase_qr_poll_step,
        _phase_qr_render,
        _phase_qr_request_code,
    )

    if not AIOHTTP_AVAILABLE:
        raise RuntimeError("aiohttp is required for WeChat QR login")

    async with aiohttp.ClientSession(trust_env=True, connector=_make_ssl_connector()) as session:
        qr = await _phase_qr_request_code(
            session, base_url=ILINK_BASE_URL, bot_type=bot_type,
        )
        if qr is None:
            return None
        qrcode_value, qrcode_url, qr_scan_data = qr
        _phase_qr_render(qrcode_url, qr_scan_data)
        state = QrLoginState(
            refresh_count=0,
            current_base_url=ILINK_BASE_URL,
            qrcode_value=qrcode_value,
            qrcode_url=qrcode_url,
            qr_scan_data=qr_scan_data,
        )
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            action, data = await _phase_qr_poll_step(session, state, bot_type=bot_type)
            if action == "confirmed":
                return _phase_qr_finalize(data_home, data)
            if action == "giveup":
                return None
            await asyncio.sleep(1)
        print("\n微信登录超时。")
        return None
