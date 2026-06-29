"""Backward-compat re-exports for ``wechat_ilink`` (ENG-13 PR-3)."""

from __future__ import annotations

import asyncio
import logging

logger = logging.getLogger(__name__)

from butler.gateway.platforms.wechat_format import (  # noqa: F401
    WECHAT_COPY_LINE_WIDTH,
    _truncate_plain,
    _split_text_for_wechat_delivery,
    _wrap_copy_friendly_lines_for_wechat,
    _split_delivery_units_for_wechat,
    _normalize_markdown_blocks,
    _split_markdown_blocks,
    _rewrite_table_block_for_wechat,
    _rewrite_headers_for_wechat,
    _split_table_row,
    _looks_like_chatty_line_for_wechat,
    _looks_like_heading_line_for_wechat,
    _should_split_short_chat_block_for_wechat,
    _pack_markdown_blocks_for_wechat,
)

try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency gate
    aiohttp = None  # type: ignore[assignment]
    AIOHTTP_AVAILABLE = False

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency gate
    default_backend = None  # type: ignore[assignment]
    Cipher = None  # type: ignore[assignment]
    algorithms = None  # type: ignore[assignment]
    modes = None  # type: ignore[assignment]
    CRYPTO_AVAILABLE = False

from butler.gateway.platforms.wechat_ilink.constants import (  # noqa: F401
    API_TIMEOUT_MS,
    BACKOFF_DELAY_SECONDS,
    CHANNEL_VERSION,
    CONFIG_TIMEOUT_MS,
    CONTENT_DEDUP_TTL_SECONDS,
    EP_GET_BOT_QR,
    EP_GET_CONFIG,
    EP_GET_QR_STATUS,
    EP_GET_UPDATES,
    EP_GET_UPLOAD_URL,
    EP_SEND_MESSAGE,
    EP_SEND_TYPING,
    ILINK_APP_CLIENT_VERSION,
    ILINK_APP_ID,
    ILINK_BASE_URL,
    ITEM_FILE,
    ITEM_IMAGE,
    ITEM_TEXT,
    ITEM_VIDEO,
    ITEM_VOICE,
    LONG_POLL_TIMEOUT_MS,
    MAX_CONSECUTIVE_FAILURES,
    MEDIA_FILE,
    MEDIA_IMAGE,
    MEDIA_VIDEO,
    MEDIA_VOICE,
    MESSAGE_ID_DEDUP_TTL_SECONDS,
    MSG_STATE_FINISH,
    MSG_TYPE_BOT,
    MSG_TYPE_USER,
    QR_TIMEOUT_MS,
    RATE_LIMIT_ERRCODE,
    RETRY_DELAY_SECONDS,
    SESSION_EXPIRED_ERRCODE,
    TYPING_START,
    TYPING_STOP,
    WECHAT_CDN_BASE_URL,
)
from butler.gateway.platforms.wechat_ilink._utils_legacy import (  # noqa: F401
    ContextTokenStore,
    TypingTicketCache,
    _account_dir,
    _account_file,
    _aes128_ecb_decrypt,
    _aes128_ecb_encrypt,
    _aes_padded_size,
    _assert_wechat_cdn_url,
    _base_info,
    _cdn_download_url,
    _cdn_upload_url,
    _content_dedup_ttl,
    _coerce_bool,
    _download_bytes,
    _extract_text,
    _guess_chat_type,
    _headers,
    _is_stale_session_ret,
    _json_dumps,
    _load_sync_buf,
    _make_ssl_connector,
    _media_reference,
    _message_id_dedup_ttl,
    _message_type_from_media,
    _mime_from_filename,
    _parse_aes_key,
    _random_wechat_uin,
    _save_sync_buf,
    _safe_id,
    _sync_buf_path,
    cache_audio_from_bytes,
    cache_document_from_bytes,
    cache_image_from_bytes,
    check_wechat_requirements,
    load_wechat_account,
    save_wechat_account,
)
from butler.gateway.platforms.wechat_ilink._utils_legacy import (
    _download_and_decrypt_media as _download_and_decrypt_media_impl,
)
from butler.gateway.platforms.wechat_ilink.registry import (  # noqa: F401
    AdapterRegistry,
    _ADAPTER_REGISTRY,
)
from butler.gateway.platforms.wechat_ilink.transport import (  # noqa: F401
    _api_get,
    _api_post,
    _get_config,
    _get_updates,
    _get_upload_url,
    _send_message,
    _send_typing,
    _upload_ciphertext,
)


async def _download_and_decrypt_media(*args, **kwargs):
    """Re-export with patch-friendly indirection (PROD-P2-01 subpackage)."""
    return await _download_and_decrypt_media_impl(*args, **kwargs)
