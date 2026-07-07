"""WeChat (iLink) pure helper utilities.

Extracted from ``wechat_ilink.py`` (audit R1-4 god-module split). All functions
and small classes in this module are pure (no dependency on the
``WeChatAdapter`` class) and are safe to import independently. The adapter
module re-exports every name defined here for backward compatibility, so
existing imports such as ``from butler.gateway.platforms.wechat_ilink
import _safe_id`` keep working unchanged.

Sub-domains:
- Crypto: AES-128-ECB + PKCS#7 (the iLink CDN media-cipher protocol)
- CDN: URL builders, host allowlist (SSRF guard), download wrapper
- Account: disk persistence helpers (wechat-setup wizard reuses them)
- Session: in-memory + disk-backed ``ContextTokenStore`` / ``TypingTicketCache``
- Sync buffer: long-poll resume cursor persistence
- Parsing: extract text from iLink item_list, guess DM-vs-group chat type
- Misc: random uin generator, JSON dumper, SSRF-safe header builder
"""

from __future__ import annotations

import base64
import hashlib
import json
from collections import OrderedDict
import logging
import mimetypes
import os
import secrets
import struct
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Awaitable, Dict, List, Optional, Tuple, TypeVar, cast
from urllib.parse import quote, urlparse

from butler.gateway.platforms.helpers import atomic_json_write  # noqa: E402

from butler.gateway.platforms.wechat_ilink._utils_legacy_ops import (
    read_json_dict_safe,
    restore_context_tokens_from_file,
    persist_context_tokens_loud,
    parse_wechat_cdn_url_loud,
    load_sync_buf_field_safe,
)
from butler.env_parse import float_env
from butler.gateway.platforms.wechat_ilink.constants import (
    ITEM_FILE,
    ITEM_IMAGE,
    ITEM_TEXT,
    ITEM_VIDEO,
    ITEM_VOICE,
)
from butler.gateway.platforms.types import MessageType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Dependency gates — try-import mirrors the original wechat_ilink module.
# Imported lazily so that ``wechat_ilink_utils`` can be loaded for tests
# even when the runtime deps are missing.
# ---------------------------------------------------------------------------

try:
    import aiohttp

    AIOHTTP_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency gate
    aiohttp = None
    AIOHTTP_AVAILABLE = False

try:
    from cryptography.hazmat.backends import default_backend
    from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

    CRYPTO_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency gate
    default_backend = None
    Cipher = None
    algorithms = None
    modes = None
    CRYPTO_AVAILABLE = False

# Constants used by helpers below (re-imported to avoid an import cycle
# with ``wechat_ilink.py``).
from butler.gateway.platforms.wechat_ilink.constants import (  # noqa: E402
    CHANNEL_VERSION,
    ILINK_APP_CLIENT_VERSION,
    ILINK_APP_ID,
    MESSAGE_ID_DEDUP_TTL_SECONDS,
    CONTENT_DEDUP_TTL_SECONDS,
    RATE_LIMIT_ERRCODE,
)

# ---------------------------------------------------------------------------
# Public diagnostic
# ---------------------------------------------------------------------------


def check_wechat_requirements() -> bool:
    """Return True when runtime dependencies for WeChat are available."""
    return AIOHTTP_AVAILABLE and CRYPTO_AVAILABLE


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def _safe_id(value: Optional[str], keep: int = 8) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "?"
    if len(raw) <= keep:
        return raw
    return raw[:keep]


def _json_dumps(payload: Dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


# ---------------------------------------------------------------------------
# Crypto — AES-128-ECB + PKCS#7 (iLink CDN media cipher)
# ---------------------------------------------------------------------------


def _pkcs7_pad(data: bytes, block_size: int = 16) -> bytes:
    pad_len = block_size - (len(data) % block_size)
    return data + bytes([pad_len] * pad_len)


def _aes128_ecb_encrypt(plaintext: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    encryptor = cipher.encryptor()
    return cast(
        bytes,
        encryptor.update(_pkcs7_pad(plaintext)) + encryptor.finalize(),
    )


def _aes128_ecb_decrypt(ciphertext: bytes, key: bytes) -> bytes:
    cipher = Cipher(algorithms.AES(key), modes.ECB(), backend=default_backend())
    decryptor = cipher.decryptor()
    padded = cast(bytes, decryptor.update(ciphertext) + decryptor.finalize())
    if not padded:
        return padded
    pad_len = padded[-1]
    if 1 <= pad_len <= 16 and padded.endswith(bytes([pad_len]) * pad_len):
        return padded[:-pad_len]
    return padded


def _aes_padded_size(size: int) -> int:
    return ((size + 1 + 15) // 16) * 16


def _random_wechat_uin() -> str:
    value = struct.unpack(">I", secrets.token_bytes(4))[0]
    return base64.b64encode(str(value).encode("utf-8")).decode("ascii")


def _base_info() -> Dict[str, Any]:
    return {"channel_version": CHANNEL_VERSION}


def _headers(token: Optional[str], body: str) -> Dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "AuthorizationType": "ilink_bot_token",
        "Content-Length": str(len(body.encode("utf-8"))),
        "X-WECHAT-UIN": _random_wechat_uin(),
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def _parse_aes_key(aes_key_b64: str) -> bytes:
    decoded = base64.b64decode(aes_key_b64)
    if len(decoded) == 16:
        return decoded
    if len(decoded) == 32:
        text = decoded.decode("ascii", errors="ignore")
        if text and all(ch in "0123456789abcdefABCDEF" for ch in text):
            return bytes.fromhex(text)
    raise ValueError(f"unexpected aes_key format ({len(decoded)} decoded bytes)")


# ---------------------------------------------------------------------------
# Account persistence (used by wechat-setup / gateway startup)
# ---------------------------------------------------------------------------


def _account_dir(data_home: str) -> Path:
    path = Path(data_home) / "wechat" / "accounts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _account_file(data_home: str, account_id: str) -> Path:
    return _account_dir(data_home) / f"{account_id}.json"


def save_wechat_account(
    data_home: str,
    *,
    account_id: str,
    token: str,
    base_url: str,
    user_id: str = "",
) -> None:
    """Persist account credentials for later reuse."""
    payload = {
        "token": token,
        "base_url": base_url,
        "user_id": user_id,
        "saved_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    path = _account_file(data_home, account_id)
    atomic_json_write(path, payload)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def load_wechat_account(data_home: str, account_id: str) -> Optional[Dict[str, Any]]:
    """Load persisted account credentials."""
    path = _account_file(data_home, account_id)
    if not path.exists():
        return None

    data = read_json_dict_safe(path)
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# In-memory + disk-backed session caches
# ---------------------------------------------------------------------------


_MAX_CONTEXT_TOKEN_ENTRIES = 5000


class ContextTokenStore:
    """Disk-backed ``context_token`` cache keyed by account + peer."""

    def __init__(self, data_home: str, *, max_entries: int = _MAX_CONTEXT_TOKEN_ENTRIES):
        self._root = _account_dir(data_home)
        self._cache: OrderedDict[str, str] = OrderedDict()
        self._lock = threading.RLock()
        self._max_entries = max(1, int(max_entries))

    def _path(self, account_id: str) -> Path:
        return self._root / f"{account_id}.context-tokens.json"

    def _key(self, account_id: str, user_id: str) -> str:
        return f"{account_id}:{user_id}"

    def restore(self, account_id: str) -> None:
        path = self._path(account_id)
        if not path.exists():
            return

        data = restore_context_tokens_from_file(path, account_id, safe_id=_safe_id)
        if data is None:
            return
        restored = 0
        with self._lock:
            for user_id, token in data.items():
                self._remember(self._key(account_id, user_id), token)
                restored += 1
        if restored:
            logger.info("wechat: restored %d context token(s) for %s", restored, _safe_id(account_id))

    def _remember(self, key: str, token: str) -> None:
        """Insert/update with LRU eviction (caller must hold ``_lock``)."""
        if key in self._cache:
            del self._cache[key]
        self._cache[key] = token
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)

    def get(self, account_id: str, user_id: str) -> Optional[str]:
        with self._lock:
            key = self._key(account_id, user_id)
            token = self._cache.get(key)
            if token is not None:
                self._cache.move_to_end(key)
            return token

    def set(self, account_id: str, user_id: str, token: str) -> None:
        with self._lock:
            self._remember(self._key(account_id, user_id), token)
            self._persist_unlocked(account_id)

    def _persist(self, account_id: str) -> None:
        with self._lock:
            self._persist_unlocked(account_id)

    def _persist_unlocked(self, account_id: str) -> None:
        prefix = f"{account_id}:"
        payload = {
            key[len(prefix) :]: value
            for key, value in self._cache.items()
            if key.startswith(prefix)
        }

        def _write() -> None:
            path = self._path(account_id)
            atomic_json_write(path, payload)
            try:
                path.chmod(0o600)
            except OSError:
                pass

        persist_context_tokens_loud(
            write_fn=_write,
            account_id=account_id,
            safe_id=_safe_id,
        )


_MAX_TYPING_TICKET_ENTRIES = 1000


class TypingTicketCache:
    """Short-lived typing ticket cache from ``getconfig``."""

    def __init__(self, ttl_seconds: float = 600.0, *, max_entries: int = _MAX_TYPING_TICKET_ENTRIES):
        self._ttl_seconds = ttl_seconds
        self._cache: OrderedDict[str, Tuple[str, float]] = OrderedDict()
        self._max_entries = max(1, int(max_entries))

    def _sweep_expired_unlocked(self) -> None:
        """Drop TTL-expired entries (caller must not hold external locks)."""
        now = time.time()
        expired = [
            user_id
            for user_id, (_, ts) in self._cache.items()
            if now - ts >= self._ttl_seconds
        ]
        for user_id in expired:
            del self._cache[user_id]

    def get(self, user_id: str) -> Optional[str]:
        entry = self._cache.get(user_id)
        if not entry:
            return None
        if time.time() - entry[1] >= self._ttl_seconds:
            self._cache.pop(user_id, None)
            return None
        self._cache.move_to_end(user_id)
        return entry[0]

    def set(self, user_id: str, ticket: str) -> None:
        now = time.time()
        if user_id in self._cache:
            del self._cache[user_id]
        self._cache[user_id] = (ticket, now)
        if len(self._cache) > self._max_entries:
            self._sweep_expired_unlocked()
        while len(self._cache) > self._max_entries:
            self._cache.popitem(last=False)


# ---------------------------------------------------------------------------
# CDN URL builders
# ---------------------------------------------------------------------------


def _cdn_download_url(cdn_base_url: str, encrypted_query_param: str) -> str:
    return f"{cdn_base_url.rstrip('/')}/download?encrypted_query_param={quote(encrypted_query_param, safe='')}"


def _cdn_upload_url(cdn_base_url: str, upload_param: str, filekey: str) -> str:
    return (
        f"{cdn_base_url.rstrip('/')}/upload"
        f"?encrypted_query_param={quote(upload_param, safe='')}"
        f"&filekey={quote(filekey, safe='')}"
    )


# ---------------------------------------------------------------------------
# De-duplication TTLs (env-overridable)
# ---------------------------------------------------------------------------


def _message_id_dedup_ttl() -> float:

    return cast(
        float,
        float_env(
            "BUTLER_WECHAT_MESSAGE_ID_DEDUP_TTL",
            float(MESSAGE_ID_DEDUP_TTL_SECONDS),
            min=5.0,
        ),
    )


def _content_dedup_ttl() -> float:

    return cast(
        float,
        float_env(
            "BUTLER_WECHAT_CONTENT_DEDUP_TTL",
            float(CONTENT_DEDUP_TTL_SECONDS),
            min=2.0,
        ),
    )


def _is_stale_session_ret(
    ret: Optional[int], errcode: Optional[int], errmsg: Optional[str],
) -> bool:
    """True when iLink returns ret=-2 / errcode=-2 with 'unknown error',
    which is a stale-session signal (same as errcode=-14) rather than
    a genuine rate limit."""
    if ret != RATE_LIMIT_ERRCODE and errcode != RATE_LIMIT_ERRCODE:
        return False
    return (errmsg or "").lower() == "unknown error"


# ---------------------------------------------------------------------------
# SSL connector (certifi fallback for Tencent CDN verification)
# ---------------------------------------------------------------------------


def _make_ssl_connector() -> Optional["aiohttp.TCPConnector"]:
    """Return a TCPConnector with a certifi CA bundle, or None if certifi is unavailable.

    Tencent's iLink server (``ilinkai.wechat.qq.com``) is not verifiable against
    some system CA stores (notably Homebrew's OpenSSL on macOS Apple Silicon).
    When ``certifi`` is installed, use its Mozilla CA bundle to guarantee
    verification. Otherwise fall back to aiohttp's default (which honors
    ``SSL_CERT_FILE`` env var via ``trust_env=True``).
    """
    try:
        import ssl
        import certifi
    except ImportError:
        return None
    if not AIOHTTP_AVAILABLE:
        return None
    ssl_ctx = ssl.create_default_context(cafile=certifi.where())
    return aiohttp.TCPConnector(ssl=ssl_ctx)


# ---------------------------------------------------------------------------
# CDN allowlist (SSRF guard) + download helpers
# ---------------------------------------------------------------------------


_WECHAT_CDN_ALLOWLIST: frozenset[str] = frozenset(
    {
        "novac2c.cdn.wechat.qq.com",
        "ilinkai.wechat.qq.com",
        "wx.qlogo.cn",
        "thirdwx.qlogo.cn",
        "res.wx.qq.com",
        "mmbiz.qpic.cn",
        "mmbiz.qlogo.cn",
    }
)


def _assert_wechat_cdn_url(url: str) -> None:
    """Raise ValueError if *url* does not point at a known WeChat CDN host."""

    scheme, host = parse_wechat_cdn_url_loud(url)

    if scheme not in ("http", "https"):
        raise ValueError(
            f"Media URL has disallowed scheme {scheme!r}; only http/https are permitted."
        )
    if host not in _WECHAT_CDN_ALLOWLIST:
        raise ValueError(
            f"Media URL host {host!r} is not in the WeChat CDN allowlist. "
            "Refusing to fetch to prevent SSRF."
        )


def _media_reference(item: Dict[str, Any], key: str) -> Dict[str, Any]:
    return (item.get(key) or {}).get("media") or {}


async def _download_bytes(
    session: "aiohttp.ClientSession",
    *,
    url: str,
    timeout_seconds: float = 60.0,
) -> bytes:
    # Use asyncio.wait_for() instead of aiohttp ClientTimeout to avoid
    # "Timeout context manager should be used inside a task" errors.
    async def _do_download() -> bytes:
        async with session.get(url) as response:
            response.raise_for_status()
            return cast(bytes, await response.read())
    return cast(
        bytes,
        await asyncio_wait_for_helper(_do_download(), timeout=timeout_seconds),
    )


async def _download_and_decrypt_media(
    session: "aiohttp.ClientSession",
    *,
    cdn_base_url: str,
    encrypted_query_param: Optional[str],
    aes_key_b64: Optional[str],
    full_url: Optional[str],
    timeout_seconds: float,
) -> bytes:

    if encrypted_query_param:
        raw = await _download_bytes(
            session,
            url=_cdn_download_url(cdn_base_url, encrypted_query_param),
            timeout_seconds=timeout_seconds,
        )
    elif full_url:
        _assert_wechat_cdn_url(full_url)
        raw = await _download_bytes(session, url=full_url, timeout_seconds=timeout_seconds)
    else:
        raise RuntimeError("media item had neither encrypt_query_param nor full_url")
    if aes_key_b64:
        raw = _aes128_ecb_decrypt(raw, _parse_aes_key(aes_key_b64))
    return cast(bytes, raw)


def _mime_from_filename(filename: str) -> str:
    return mimetypes.guess_type(filename)[0] or "application/octet-stream"


# ---------------------------------------------------------------------------
# Inbound message parsing
# ---------------------------------------------------------------------------


def _coerce_bool(value: Any, default: bool = True) -> bool:
    """Coerce a config value to bool, tolerating strings like ``"true"``."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if not text:
        return default
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _extract_text(item_list: List[Dict[str, Any]]) -> str:
    # Lazy import to avoid a circular reference at module load (the
    # constants module does not depend on this module).

    for item in item_list:
        if item.get("type") == ITEM_TEXT:
            text = str((item.get("text_item") or {}).get("text") or "")
            ref = item.get("ref_msg") or {}
            ref_item = ref.get("message_item") or {}
            ref_type = ref_item.get("type")
            if ref_type in (ITEM_IMAGE, ITEM_VIDEO, ITEM_FILE, ITEM_VOICE):
                title = ref.get("title") or ""
                prefix = f"[引用媒体: {title}]\n" if title else "[引用媒体]\n"
                return f"{prefix}{text}".strip()
            if ref_item:
                parts: List[str] = []
                if ref.get("title"):
                    parts.append(str(ref["title"]))
                ref_text = _extract_text([ref_item])
                if ref_text:
                    parts.append(ref_text)
                if parts:
                    return f"[引用: {' | '.join(parts)}]\n{text}".strip()
            return text
    for item in item_list:
        if item.get("type") == ITEM_VOICE:
            voice_text = str((item.get("voice_item") or {}).get("text") or "")
            if voice_text:
                return voice_text
    return ""


def _message_type_from_media(media_types: List[str], text: str) -> Any:
    # Late import keeps ``wechat_ilink_constants`` dependency-free.

    if any(m.startswith("image/") for m in media_types):
        return MessageType.PHOTO
    if any(m.startswith("video/") for m in media_types):
        return MessageType.VIDEO
    if any(m.startswith("audio/") for m in media_types):
        return MessageType.VOICE
    if media_types:
        return MessageType.DOCUMENT
    if text.startswith("/"):
        return MessageType.COMMAND
    return MessageType.TEXT


def _guess_chat_type(message: Dict[str, Any], account_id: str) -> Tuple[str, str]:
    room_id = str(message.get("room_id") or message.get("chat_room_id") or "").strip()
    to_user_id = str(message.get("to_user_id") or "").strip()
    is_group = bool(room_id) or (
        to_user_id and account_id and to_user_id != account_id and message.get("msg_type") == 1
    )
    if is_group:
        return "group", room_id or to_user_id or str(message.get("from_user_id") or "")
    return "dm", str(message.get("from_user_id") or "")


# ---------------------------------------------------------------------------
# Sync buffer (long-poll resume cursor)
# ---------------------------------------------------------------------------


def _sync_buf_path(data_home: str, account_id: str) -> Path:
    return _account_dir(data_home) / f"{account_id}.sync.json"


def _load_sync_buf(data_home: str, account_id: str) -> str:
    path = _sync_buf_path(data_home, account_id)
    if not path.exists():
        return ""

    return cast(str, load_sync_buf_field_safe(path))


def _save_sync_buf(data_home: str, account_id: str, sync_buf: str) -> None:
    path = _sync_buf_path(data_home, account_id)
    atomic_json_write(path, {"get_updates_buf": sync_buf})


# ---------------------------------------------------------------------------
# Media cache (write inbound decrypted bytes to a temp file)
# ---------------------------------------------------------------------------


def cache_image_from_bytes(data: bytes, ext: str) -> str:
    import tempfile
    fd, path = tempfile.mkstemp(suffix=ext or ".jpg")
    os.write(fd, data)
    os.close(fd)
    return path


def cache_document_from_bytes(data: bytes, filename: str) -> str:
    import tempfile
    suffix = Path(filename).suffix if filename else ".bin"
    fd, path = tempfile.mkstemp(suffix=suffix)
    os.write(fd, data)
    os.close(fd)
    return path


def cache_audio_from_bytes(data: bytes, ext: str) -> str:
    return cache_document_from_bytes(data, f"voice{ext or '.silk'}")


# ---------------------------------------------------------------------------
# Internal: ``asyncio.wait_for`` wrapper to keep the original behaviour
# documented inline at the original call-sites. Tests that patch
# ``butler.gateway.platforms.wechat_ilink.asyncio.wait_for`` will continue
# to work because the adapter module re-imports ``asyncio`` and the
# original function definition is still importable.
# ---------------------------------------------------------------------------


_T = TypeVar("_T")


async def asyncio_wait_for_helper(awaitable: Awaitable[_T], timeout: float) -> _T:
    import asyncio

    return await asyncio.wait_for(awaitable, timeout)
