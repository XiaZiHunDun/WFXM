"""WeChat (iLink) constants and enums.

Extracted from ``wechat_ilink.py`` (audit R1-4 god-module split) so the
adapter module is no longer the canonical home for these names. The
adapter module re-exports them so existing imports such as
``from butler.gateway.platforms.wechat_ilink import SESSION_EXPIRED_ERRCODE``
keep working unchanged.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# iLink endpoint URLs
# ---------------------------------------------------------------------------

ILINK_BASE_URL = "https://ilinkai.weixin.qq.com"
WECHAT_CDN_BASE_URL = "https://novac2c.cdn.weixin.qq.com/c2c"

# Channel/app identity
ILINK_APP_ID = "bot"
CHANNEL_VERSION = "2.2.0"
ILINK_APP_CLIENT_VERSION = (2 << 16) | (2 << 8) | 0

# Endpoint paths (relative to ``ILINK_BASE_URL``)
EP_GET_UPDATES = "ilink/bot/getupdates"
EP_SEND_MESSAGE = "ilink/bot/sendmessage"
EP_SEND_TYPING = "ilink/bot/sendtyping"
EP_GET_CONFIG = "ilink/bot/getconfig"
EP_GET_UPLOAD_URL = "ilink/bot/getuploadurl"
EP_GET_BOT_QR = "ilink/bot/get_bot_qrcode"
EP_GET_QR_STATUS = "ilink/bot/get_qrcode_status"

# ---------------------------------------------------------------------------
# Polling / timeouts (milliseconds unless noted)
# ---------------------------------------------------------------------------

LONG_POLL_TIMEOUT_MS = 35_000
API_TIMEOUT_MS = 15_000
CONFIG_TIMEOUT_MS = 10_000
QR_TIMEOUT_MS = 35_000

# ---------------------------------------------------------------------------
# Retry / backoff policy
# ---------------------------------------------------------------------------

MAX_CONSECUTIVE_FAILURES = 3
RETRY_DELAY_SECONDS = 2
BACKOFF_DELAY_SECONDS = 30

# ---------------------------------------------------------------------------
# Error codes returned by the iLink API
# ---------------------------------------------------------------------------

SESSION_EXPIRED_ERRCODE = -14
# iLink frequency limit — backoff and retry
RATE_LIMIT_ERRCODE = -2

# ---------------------------------------------------------------------------
# De-duplication TTLs (seconds)
# ---------------------------------------------------------------------------

MESSAGE_ID_DEDUP_TTL_SECONDS = 300
# Short window: only suppress iLink duplicate delivery bursts, not intentional
# user resends (M4).
CONTENT_DEDUP_TTL_SECONDS = 20

# ---------------------------------------------------------------------------
# Media / item / message type enums (iLink payload vocabulary)
# ---------------------------------------------------------------------------

# media_type for getuploadurl
MEDIA_IMAGE = 1
MEDIA_VIDEO = 2
MEDIA_FILE = 3
MEDIA_VOICE = 4

# item.type inside an item_list
ITEM_TEXT = 1
ITEM_IMAGE = 2
ITEM_VOICE = 3
ITEM_FILE = 4
ITEM_VIDEO = 5

# message_type / message_state on the send-message envelope
MSG_TYPE_USER = 1
MSG_TYPE_BOT = 2
MSG_STATE_FINISH = 2

# status field for sendtyping
TYPING_START = 1
TYPING_STOP = 2
