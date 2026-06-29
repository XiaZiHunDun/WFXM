"""WeChat (iLink) platform adapter — Butler-native port.

Connects Butler Gateway to WeChat personal accounts via Tencent's iLink Bot API.

Design notes:
- Long-poll ``getupdates`` drives inbound delivery.
- Every outbound reply must echo the latest ``context_token`` for the peer.
- Media files move through an AES-128-ECB encrypted CDN protocol.
- QR login is exposed as a helper for the gateway setup wizard.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# Backward-compat re-exports (constants, utils, transport, registry, ``_*`` helpers).
from butler.gateway.platforms.wechat_ilink import _compat as _wechat_compat

for _name in dir(_wechat_compat):
    if _name.startswith("__"):
        continue
    globals()[_name] = getattr(_wechat_compat, _name)
del _wechat_compat, _name

from butler.gateway.platforms.wechat_ilink.adapter import WeChatAdapter
from butler.gateway.platforms.wechat_ilink.qr_login import qr_login


async def send_wechat_direct(
    *,
    extra: Dict[str, Any],
    token: Optional[str],
    chat_id: str,
    message: str,
    media_files: Optional[List[Tuple[str, bool]]] = None,
) -> Dict[str, Any]:
    """One-shot send helper for ``send_message`` and cron delivery."""
    from butler.gateway.platforms.wechat_ilink.direct import send_wechat_direct as _send

    return await _send(
        extra=extra,
        token=token,
        chat_id=chat_id,
        message=message,
        media_files=media_files,
    )
