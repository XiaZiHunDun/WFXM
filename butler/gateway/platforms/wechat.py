"""WeChat gateway platform (Butler-native iLink adapter)."""

from butler.gateway.platforms.wechat_ilink import (
    WeChatAdapter,
    check_wechat_requirements,
    qr_login,
)

__all__ = ["WeChatAdapter", "check_wechat_requirements", "qr_login"]
