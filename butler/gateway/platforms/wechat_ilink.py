"""
WeChat (iLink) platform adapter — Butler-native port.

Connects Butler Gateway to WeChat personal accounts via Tencent's iLink Bot API.

Design notes:
- Long-poll ``getupdates`` drives inbound delivery.
- Every outbound reply must echo the latest ``context_token`` for the peer.
- Media files move through an AES-128-ECB encrypted CDN protocol.
- QR login is exposed as a helper for the gateway setup wizard.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import mimetypes
import os
import secrets
import struct
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

from butler.gateway.platforms.wechat_format import (  # noqa: F401, E402
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

from butler.gateway.platforms.types import PlatformConfig  # noqa: E402
from butler.gateway.platforms.helpers import MessageDeduplicator, atomic_json_write  # noqa: E402
from butler.gateway.platforms.types import MessageEvent, MessageType, SendResult  # noqa: E402
from butler.gateway.platforms.base import ButlerPlatformAdapter  # noqa: E402
from butler.config import get_butler_home  # noqa: E402
# Re-export all constants/enums from the extracted sibling module so
# ``from butler.gateway.platforms.wechat_ilink import SESSION_EXPIRED_ERRCODE``
# (and similar) keeps working unchanged after audit R1-4 split.
from butler.gateway.platforms.wechat_ilink_constants import (  # noqa: E402, F401
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
# Re-export utility helpers from the extracted utils sibling module.
# See ``wechat_ilink_utils.py`` for the canonical home; this block is a
# shim for backward compatibility after audit R1-4 split.
from butler.gateway.platforms.wechat_ilink_utils import (  # noqa: E402, F401
    ContextTokenStore,
    TypingTicketCache,
    _account_dir,
    _account_file,
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
# Async download helper stays in this module to avoid a circular import
# with the CDN/utility module — tests patch it on this module path.
from butler.gateway.platforms.wechat_ilink_utils import (  # noqa: E402, F401
    _download_and_decrypt_media,
)


# R1-12 — thread-safe registry for live WeChat adapters. Replaces the
# module-level ``_LIVE_ADAPTERS: Dict`` whose unguarded concurrent
# register/get/pop across the long-poll loop and the one-shot
# ``send_wechat_direct`` path was the audit H finding. The new
# registry pairs a ``weakref.WeakValueDictionary`` (so dropped
# adapters are reclaimed automatically) with a ``threading.RLock``
# (so concurrent mutations are serialised).
from butler.gateway.platforms.wechat_ilink_registry import (  # noqa: E402
    AdapterRegistry,
    _ADAPTER_REGISTRY,
)


async def _api_post(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    endpoint: str,
    payload: Dict[str, Any],
    token: Optional[str],
    timeout_ms: int,
) -> Dict[str, Any]:
    body = _json_dumps({**payload, "base_info": _base_info()})
    url = f"{base_url.rstrip('/')}/{endpoint}"
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.post(url, data=body, headers=_headers(token, body), timeout=timeout) as response:
        raw = await response.text()
        if not response.ok:
            raise RuntimeError(f"iLink POST {endpoint} HTTP {response.status}: {raw[:200]}")
        return json.loads(raw)


async def _api_get(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    endpoint: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    url = f"{base_url.rstrip('/')}/{endpoint}"
    headers = {
        "iLink-App-Id": ILINK_APP_ID,
        "iLink-App-ClientVersion": str(ILINK_APP_CLIENT_VERSION),
    }
    timeout = aiohttp.ClientTimeout(total=timeout_ms / 1000)
    async with session.get(url, headers=headers, timeout=timeout) as response:
        raw = await response.text()
        if not response.ok:
            raise RuntimeError(f"iLink GET {endpoint} HTTP {response.status}: {raw[:200]}")
        return json.loads(raw)


async def _get_updates(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    sync_buf: str,
    timeout_ms: int,
) -> Dict[str, Any]:
    try:
        return await _api_post(
            session,
            base_url=base_url,
            endpoint=EP_GET_UPDATES,
            payload={"get_updates_buf": sync_buf},
            token=token,
            timeout_ms=timeout_ms,
        )
    except asyncio.TimeoutError:
        return {"ret": 0, "msgs": [], "get_updates_buf": sync_buf}


async def _send_message(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    to: str,
    text: str,
    context_token: Optional[str],
    client_id: str,
) -> Dict[str, Any]:
    """Send a text message via iLink sendmessage API.

    Returns the raw API response dict (may contain error codes like
    ``errcode: -14`` for session expiry that the caller can inspect).
    """
    if not text or not text.strip():
        raise ValueError("_send_message: text must not be empty")
    message: Dict[str, Any] = {
        "from_user_id": "",
        "to_user_id": to,
        "client_id": client_id,
        "message_type": MSG_TYPE_BOT,
        "message_state": MSG_STATE_FINISH,
        "item_list": [{"type": ITEM_TEXT, "text_item": {"text": text}}],
    }
    if context_token:
        message["context_token"] = context_token
    return await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_SEND_MESSAGE,
        payload={"msg": message},
        token=token,
        timeout_ms=API_TIMEOUT_MS,
    )


async def _send_typing(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    to_user_id: str,
    typing_ticket: str,
    status: int,
) -> None:
    await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_SEND_TYPING,
        payload={
            "ilink_user_id": to_user_id,
            "typing_ticket": typing_ticket,
            "status": status,
        },
        token=token,
        timeout_ms=CONFIG_TIMEOUT_MS,
    )


async def _get_config(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    user_id: str,
    context_token: Optional[str],
) -> Dict[str, Any]:
    payload: Dict[str, Any] = {"ilink_user_id": user_id}
    if context_token:
        payload["context_token"] = context_token
    return await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_GET_CONFIG,
        payload=payload,
        token=token,
        timeout_ms=CONFIG_TIMEOUT_MS,
    )


async def _get_upload_url(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    token: str,
    to_user_id: str,
    media_type: int,
    filekey: str,
    rawsize: int,
    rawfilemd5: str,
    filesize: int,
    aeskey_hex: str,
) -> Dict[str, Any]:
    return await _api_post(
        session,
        base_url=base_url,
        endpoint=EP_GET_UPLOAD_URL,
        payload={
            "filekey": filekey,
            "media_type": media_type,
            "to_user_id": to_user_id,
            "rawsize": rawsize,
            "rawfilemd5": rawfilemd5,
            "filesize": filesize,
            "no_need_thumb": True,
            "aeskey": aeskey_hex,
        },
        token=token,
        timeout_ms=API_TIMEOUT_MS,
    )


async def _upload_ciphertext(
    session: "aiohttp.ClientSession",
    *,
    ciphertext: bytes,
    upload_url: str,
) -> str:
    """Upload encrypted media to the CDN.

    Accepts either a constructed CDN URL (from upload_param) or a direct
    upload_full_url — both use POST with the raw ciphertext as the body.
    """
    # Use asyncio.wait_for() instead of aiohttp ClientTimeout to avoid
    # "Timeout context manager should be used inside a task" errors when
    # invoked via asyncio.run_coroutine_threadsafe() from cron jobs.
    async def _do_upload() -> str:
        async with session.post(
            upload_url,
            data=ciphertext,
            headers={"Content-Type": "application/octet-stream"},
        ) as response:
            if response.status == 200:
                encrypted_param = response.headers.get("x-encrypted-param")
                if encrypted_param:
                    await response.read()
                    return encrypted_param
                raw = await response.text()
                raise RuntimeError(f"CDN upload missing x-encrypted-param header: {raw[:200]}")
            raw = await response.text()
            raise RuntimeError(f"CDN upload HTTP {response.status}: {raw[:200]}")
    return await asyncio.wait_for(_do_upload(), timeout=120)


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
    # R1-4b: thin state-machine orchestrator. All heavy lifting
    # (HTTP fetch, terminal QR rendering, poll-dispatch, refresh,
    # persistence) lives in ``wechat_ilink_phases.py``.
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


class WeChatAdapter(ButlerPlatformAdapter):
    """Butler-native WeChat (iLink Bot API) adapter."""

    MAX_MESSAGE_LENGTH = 2000

    # WeChat does not support editing sent messages — streaming must use the
    # fallback "send-final-only" path so the cursor (▉) is never left visible.
    SUPPORTS_MESSAGE_EDITING = False

    def __init__(self, config: PlatformConfig):
        # R1-4a: thin orchestrator — delegates to 4 phase functions in
        # ``wechat_ilink_phases.py``. The phases collectively own the
        # env/config/extra resolution; this method only sets up the
        # transport-agnostic state.
        super().__init__(config, "wechat")
        self._data_home = str(get_butler_home())
        self._token_store = ContextTokenStore(self._data_home)
        self._typing_cache = TypingTicketCache()
        self._poll_session: Optional[aiohttp.ClientSession] = None
        self._send_session: Optional[aiohttp.ClientSession] = None
        self._poll_task: Optional[asyncio.Task] = None
        self._bg_typing_tasks: set[asyncio.Task] = set()
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_init_account,
            _phase_init_chunks,
            _phase_init_dedup,
            _phase_init_policies,
        )

        _phase_init_account(self, config)
        _phase_init_chunks(self, config)
        _phase_init_policies(self, config)
        _phase_init_dedup(self)

    @staticmethod
    def _coerce_list(value: Any) -> List[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return [item.strip() for item in value.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [str(value).strip()] if str(value).strip() else []

    def _schedule_typing_ticket_bg(self, user_id: str, context_token: Optional[str]) -> None:
        """Fire-and-forget typing-ticket fetch, but retain the task on the adapter
        so disconnect() can cancel it before _poll_session closes."""
        task = asyncio.create_task(
            self._maybe_fetch_typing_ticket(user_id, context_token)
        )
        self._bg_typing_tasks.add(task)
        task.add_done_callback(self._bg_typing_tasks.discard)

    async def connect(self) -> bool:
        # R1-4a: thin orchestrator — delegates to 2 phase functions in
        # ``wechat_ilink_phases.py``. Validation gates return; the
        # open-sessions phase does the heavy transport setup.
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_connect_open_sessions,
            _phase_connect_validate,
        )

        if not _phase_connect_validate(self):
            return False
        _phase_connect_open_sessions(self)
        return True

    async def disconnect(self) -> None:
        _ADAPTER_REGISTRY.unregister(self._token)
        self._running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        self._poll_task = None
        # Cancel any retained background typing-ticket fetches BEFORE we close
        # _poll_session — otherwise they will keep a reference to a closed session
        # and crash on the next await.
        pending_bg = [t for t in self._bg_typing_tasks if not t.done()]
        for t in pending_bg:
            t.cancel()
        if pending_bg:
            await asyncio.gather(*pending_bg, return_exceptions=True)
        self._bg_typing_tasks.clear()
        if self._poll_session and not self._poll_session.closed:
            await self._poll_session.close()
        self._poll_session = None
        if self._send_session and not self._send_session.closed:
            await self._send_session.close()
        self._send_session = None
        self._release_platform_lock()
        self._mark_disconnected()
        logger.info("[%s] Disconnected", self.name)

    async def _poll_loop(self) -> None:
        # R1-4a: thin orchestrator — delegates per-iteration response
        # handling to ``_phase_poll_handle_response``. The backoff
        # ladder + message dispatch are pulled into private helpers
        # below; this method owns the loop, the transport call, and
        # the cancellation + error envelope only.
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_poll_handle_response,
        )

        assert self._poll_session is not None
        sync_buf = _load_sync_buf(self._data_home, self._account_id)
        timeout_ms = LONG_POLL_TIMEOUT_MS
        consecutive_failures = 0

        while self._running:
            try:
                response = await _get_updates(
                    self._poll_session,
                    base_url=self._base_url,
                    token=self._token,
                    sync_buf=sync_buf,
                    timeout_ms=timeout_ms,
                )
                suggested_timeout = response.get("longpolling_timeout_ms")
                if isinstance(suggested_timeout, int) and suggested_timeout > 0:
                    timeout_ms = suggested_timeout
                consecutive_failures = await self._dispatch_poll_response(
                    response, consecutive_failures, _phase_poll_handle_response,
                )
            except asyncio.CancelledError:
                break
            except Exception as exc:
                consecutive_failures = await self._handle_poll_exception(
                    exc, consecutive_failures,
                )

    async def _dispatch_poll_response(
        self,
        response: Dict[str, Any],
        consecutive_failures: int,
        handle_response: Any,
    ) -> int:
        """Dispatch one poll response. Returns the updated failure counter."""
        signal, messages = handle_response(self, response)
        if signal == "session_expired":
            await asyncio.sleep(600)
            return 0
        ret = response.get("ret", 0)
        errcode = response.get("errcode", 0)
        if ret not in (0, None) or errcode not in (0, None):
            consecutive_failures += 1
            logger.warning(
                "[%s] getUpdates failed ret=%s errcode=%s errmsg=%s (%d/%d)",
                self.name, ret, errcode, response.get("errmsg", ""),
                consecutive_failures, MAX_CONSECUTIVE_FAILURES,
            )
            await asyncio.sleep(self._poll_backoff_seconds(consecutive_failures))
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                return 0
            return consecutive_failures
        for message in messages:
            # Serialize within a poll batch — create_task caused registry races.
            await self._process_message_safe(message)
        return 0

    @staticmethod
    def _poll_backoff_seconds(consecutive_failures: int) -> float:
        """Pick BACKOFF_DELAY (>=MAX) or RETRY_DELAY based on failure ladder."""
        return (
            BACKOFF_DELAY_SECONDS
            if consecutive_failures >= MAX_CONSECUTIVE_FAILURES
            else RETRY_DELAY_SECONDS
        )

    async def _handle_poll_exception(
        self, exc: Exception, consecutive_failures: int,
    ) -> int:
        """Outer-exception backoff branch for ``_poll_loop``. Returns updated counter."""
        consecutive_failures += 1
        logger.error(
            "[%s] poll error (%d/%d): %s",
            self.name, consecutive_failures, MAX_CONSECUTIVE_FAILURES, exc,
        )
        await asyncio.sleep(self._poll_backoff_seconds(consecutive_failures))
        if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
            return 0
        return consecutive_failures

    async def _process_message_safe(self, message: Dict[str, Any]) -> None:
        try:
            await self._process_message(message)
        except Exception as exc:
            logger.error(
                "[%s] unhandled inbound error from=%s: %s",
                self.name,
                _safe_id(message.get("from_user_id")),
                exc,
                exc_info=True,
            )

    async def _process_message(self, message: Dict[str, Any]) -> None:
        # R1-4a: thin orchestrator — delegates dedup / chat-policy /
        # event-construction to 3 phase functions in
        # ``wechat_ilink_phases.py``. This method owns the iLink
        # self-id skip + token-store write + media collection.
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_inbound_build_event,
            _phase_inbound_chat_policy,
            _phase_inbound_dedup,
        )

        assert self._poll_session is not None
        sender_id = str(message.get("from_user_id") or "").strip()
        if not sender_id:
            return
        if sender_id == self._account_id:
            return

        message_id = str(message.get("message_id") or "").strip()
        item_list = message.get("item_list") or []
        text = _extract_text(item_list)

        if not _phase_inbound_dedup(self, message, sender_id, text):
            return

        chat_type, effective_chat_id = _guess_chat_type(message, self._account_id)
        if not _phase_inbound_chat_policy(self, chat_type, effective_chat_id, sender_id):
            return

        context_token = str(message.get("context_token") or "").strip()
        if context_token:
            self._token_store.set(self._account_id, sender_id, context_token)
        self._schedule_typing_ticket_bg(sender_id, context_token or None)

        media_paths: List[str] = []
        media_types: List[str] = []
        for item in item_list:
            await self._collect_media(item, media_paths, media_types)
            ref_message = item.get("ref_msg") or {}
            ref_item = ref_message.get("message_item")
            if isinstance(ref_item, dict):
                await self._collect_media(ref_item, media_paths, media_types)

        if not text and not media_paths:
            return

        event = _phase_inbound_build_event(
            self, message, sender_id, text, media_paths, media_types,
            effective_chat_id, chat_type, message_id,
        )
        await self.handle_message(event)

    def _is_dm_allowed(self, sender_id: str) -> bool:
        if self._dm_policy == "disabled":
            return False
        if self._dm_policy == "allowlist":
            return sender_id in self._allow_from
        return True

    async def _collect_media(self, item: Dict[str, Any], media_paths: List[str], media_types: List[str]) -> None:
        item_type = item.get("type")
        if item_type == ITEM_IMAGE:
            path = await self._download_image(item)
            if path:
                media_paths.append(path)
                media_types.append("image/jpeg")
        elif item_type == ITEM_VIDEO:
            path = await self._download_video(item)
            if path:
                media_paths.append(path)
                media_types.append("video/mp4")
        elif item_type == ITEM_FILE:
            path, mime = await self._download_file(item)
            if path:
                media_paths.append(path)
                media_types.append(mime)
        elif item_type == ITEM_VOICE:
            voice_path = await self._download_voice(item)
            if voice_path:
                media_paths.append(voice_path)
                media_types.append("audio/silk")

    async def _download_image(self, item: Dict[str, Any]) -> Optional[str]:
        media = _media_reference(item, "image_item")
        try:
            data = await _download_and_decrypt_media(
                self._poll_session,
                cdn_base_url=self._cdn_base_url,
                encrypted_query_param=media.get("encrypt_query_param"),
                aes_key_b64=(item.get("image_item") or {}).get("aeskey")
                and base64.b64encode(bytes.fromhex(str((item.get("image_item") or {}).get("aeskey")))).decode("ascii")
                or media.get("aes_key"),
                full_url=media.get("full_url"),
                timeout_seconds=30.0,
            )
            return cache_image_from_bytes(data, ".jpg")
        except Exception as exc:
            logger.warning("[%s] image download failed: %s", self.name, exc)
            return None

    async def _download_video(self, item: Dict[str, Any]) -> Optional[str]:
        media = _media_reference(item, "video_item")
        try:
            data = await _download_and_decrypt_media(
                self._poll_session,
                cdn_base_url=self._cdn_base_url,
                encrypted_query_param=media.get("encrypt_query_param"),
                aes_key_b64=media.get("aes_key"),
                full_url=media.get("full_url"),
                timeout_seconds=120.0,
            )
            return cache_document_from_bytes(data, "video.mp4")
        except Exception as exc:
            logger.warning("[%s] video download failed: %s", self.name, exc)
            return None

    async def _download_file(self, item: Dict[str, Any]) -> Tuple[Optional[str], str]:
        file_item = item.get("file_item") or {}
        media = file_item.get("media") or {}
        filename = str(file_item.get("file_name") or "document.bin")
        mime = _mime_from_filename(filename)
        try:
            data = await _download_and_decrypt_media(
                self._poll_session,
                cdn_base_url=self._cdn_base_url,
                encrypted_query_param=media.get("encrypt_query_param"),
                aes_key_b64=media.get("aes_key"),
                full_url=media.get("full_url"),
                timeout_seconds=60.0,
            )
            return cache_document_from_bytes(data, filename), mime
        except Exception as exc:
            logger.warning("[%s] file download failed: %s", self.name, exc)
            return None, mime

    async def _download_voice(self, item: Dict[str, Any]) -> Optional[str]:
        voice_item = item.get("voice_item") or {}
        media = voice_item.get("media") or {}
        if voice_item.get("text"):
            return None
        try:
            data = await _download_and_decrypt_media(
                self._poll_session,
                cdn_base_url=self._cdn_base_url,
                encrypted_query_param=media.get("encrypt_query_param"),
                aes_key_b64=media.get("aes_key"),
                full_url=media.get("full_url"),
                timeout_seconds=60.0,
            )
            return cache_audio_from_bytes(data, ".silk")
        except Exception as exc:
            logger.warning("[%s] voice download failed: %s", self.name, exc)
            return None

    async def _maybe_fetch_typing_ticket(self, user_id: str, context_token: Optional[str]) -> None:
        if not self._poll_session or not self._token:
            return
        if self._typing_cache.get(user_id):
            return
        try:
            response = await _get_config(
                self._poll_session,
                base_url=self._base_url,
                token=self._token,
                user_id=user_id,
                context_token=context_token,
            )
            typing_ticket = str(response.get("typing_ticket") or "")
            if typing_ticket:
                self._typing_cache.set(user_id, typing_ticket)
        except Exception as exc:
            logger.debug("[%s] getConfig failed for %s: %s", self.name, _safe_id(user_id), exc)

    async def _ensure_typing_ticket_for_event(self, event: MessageEvent) -> None:
        """Await typing ticket before first ``send_typing`` (avoids inbound race)."""
        if not event.source:
            return
        chat_id = event.source.chat_id
        timeout = float(os.getenv("BUTLER_GATEWAY_TYPING_FETCH_TIMEOUT_SECONDS", "2") or "2")
        context_token = ""
        raw = event.raw_message if isinstance(event.raw_message, dict) else {}
        context_token = str(raw.get("context_token") or "").strip()
        try:
            await asyncio.wait_for(
                self._maybe_fetch_typing_ticket(chat_id, context_token or None),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.debug("[%s] typing ticket fetch timed out for %s", self.name, _safe_id(chat_id))

    def _split_text(self, content: str) -> List[str]:
        return _split_text_for_wechat_delivery(
            content, self.MAX_MESSAGE_LENGTH, self._split_multiline_messages,
        )

    async def _send_text_chunk(
        self,
        *,
        chat_id: str,
        chunk: str,
        context_token: Optional[str],
        client_id: str,
    ) -> None:
        """Send a single text chunk with per-chunk retry and backoff.

        R1-4a: thin orchestrator — delegates per-attempt transport +
        response classification to 2 phase functions in
        ``wechat_ilink_phases.py``. On session-expired (errcode -14)
        retries once *without* ``context_token`` (tokenless fallback).
        """
        from butler.gateway.platforms.wechat_ilink_phases import (
            WeChatSendState,
            _phase_chunk_attempt,
            _phase_chunk_handle_response,
        )

        last_error: Optional[Exception] = None
        state = WeChatSendState()
        for attempt in range(self._send_chunk_retries + 1):
            try:
                resp = await _phase_chunk_attempt(
                    self, chat_id=chat_id, chunk=chunk,
                    context_token=context_token, client_id=client_id,
                )
                action, new_token, err = _phase_chunk_handle_response(
                    self, resp, chat_id=chat_id,
                    context_token=context_token, state=state,
                )
                if action == "ok":
                    return
                if action == "retry_without_token":
                    context_token = new_token
                elif action == "raise":
                    raise err
                elif action == "retry":
                    last_error = err
                    if attempt >= self._send_chunk_retries:
                        break
                    await self._backoff_for_rate_limit(chat_id, attempt)
            except Exception as exc:
                last_error = exc
                if attempt >= self._send_chunk_retries:
                    break
                await self._backoff_for_transport_error(chat_id, attempt, exc)
        assert last_error is not None
        raise last_error

    async def _backoff_for_rate_limit(self, chat_id: str, attempt: int) -> None:
        """Sleep per the rate-limit backoff ladder (exponential, capped)."""
        cap = 90.0
        try:
            cap = max(
                10.0,
                float(os.getenv("BUTLER_WECHAT_RATE_LIMIT_BACKOFF_MAX", "90")),
            )
        except ValueError:
            cap = 90.0
        wait = min(cap, self._send_chunk_retry_delay_seconds * (3 ** attempt))
        logger.warning(
            "[%s] rate limited for %s; backing off %.1fs before retry",
            self.name, _safe_id(chat_id), wait,
        )
        await asyncio.sleep(wait)

    async def _backoff_for_transport_error(
        self, chat_id: str, attempt: int, exc: Exception,
    ) -> None:
        """Linear backoff after a transport-level failure (non-rate-limit)."""
        wait = self._send_chunk_retry_delay_seconds * (attempt + 1)
        logger.warning(
            "[%s] send chunk failed to=%s attempt=%d/%d, retrying in %.2fs: %s",
            self.name, _safe_id(chat_id),
            attempt + 1, self._send_chunk_retries + 1, wait, exc,
        )
        if wait > 0:
            await asyncio.sleep(wait)

    async def send(
        self,
        chat_id: str,
        content: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        # R1-4a: thin orchestrator — extracts media + local files, then
        # delegates delivery to 2 phase functions in
        # ``wechat_ilink_phases.py``. This method owns the
        # connection-state gate + outer try/except only.
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_send_attachments,
            _phase_send_text_chunks,
        )

        del reply_to
        if not self._send_session or not self._token:
            return SendResult(success=False, error="Not connected")
        context_token = self._token_store.get(self._account_id, chat_id)

        # Extract MEDIA: tags and bare local file paths before text delivery.
        media_files, cleaned_content = self.extract_media(content)
        _, image_cleaned = self.extract_images(cleaned_content)
        local_files, final_content = self.extract_local_files(image_cleaned)

        try:
            await _phase_send_attachments(
                self, media_files, local_files, chat_id, metadata,
            )
            last_message_id = await _phase_send_text_chunks(
                self, final_content, chat_id, context_token,
            )
            return SendResult(success=True, message_id=last_message_id)
        except Exception as exc:
            logger.error("[%s] send failed to=%s: %s", self.name, _safe_id(chat_id), exc)
            return SendResult(success=False, error=str(exc))

    async def send_typing(self, chat_id: str, metadata: Optional[Dict[str, Any]] = None) -> None:
        if not self._send_session or not self._token:
            return
        typing_ticket = self._typing_cache.get(chat_id)
        if not typing_ticket:
            return
        try:
            await _send_typing(
                self._send_session,
                base_url=self._base_url,
                token=self._token,
                to_user_id=chat_id,
                typing_ticket=typing_ticket,
                status=TYPING_START,
            )
        except Exception as exc:
            logger.debug("[%s] typing start failed for %s: %s", self.name, _safe_id(chat_id), exc)

    async def stop_typing(self, chat_id: str) -> None:
        if not self._send_session or not self._token:
            return
        typing_ticket = self._typing_cache.get(chat_id)
        if not typing_ticket:
            return
        try:
            await _send_typing(
                self._send_session,
                base_url=self._base_url,
                token=self._token,
                to_user_id=chat_id,
                typing_ticket=typing_ticket,
                status=TYPING_STOP,
            )
        except Exception as exc:
            logger.debug("[%s] typing stop failed for %s: %s", self.name, _safe_id(chat_id), exc)

    async def send_image(
        self,
        chat_id: str,
        image_url: str,
        caption: str,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if image_url.startswith(("http://", "https://")):
            file_path = await self._download_remote_media(image_url)
            cleanup = True
        else:
            file_path = image_url.replace("file://", "")
            if not os.path.isabs(file_path):
                file_path = os.path.abspath(file_path)
            cleanup = False
        try:
            return await self.send_document(chat_id, file_path, caption=caption, metadata=metadata)
        finally:
            if cleanup and file_path and os.path.exists(file_path):
                try:
                    os.unlink(file_path)
                except OSError:
                    pass

    async def send_image_file(
        self,
        chat_id: str,
        image_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        del reply_to, kwargs
        return await self.send_document(
            chat_id=chat_id,
            file_path=image_path,
            caption=caption,
            metadata=metadata,
        )

    async def send_document(
        self,
        chat_id: str,
        file_path: str,
        caption: Optional[str] = None,
        file_name: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        **kwargs,
    ) -> SendResult:
        del file_name, reply_to, metadata, kwargs
        if not self._send_session or not self._token:
            return SendResult(success=False, error="Not connected")
        try:
            message_id = await self._send_file(chat_id, file_path, caption or "")
            return SendResult(success=True, message_id=message_id)
        except Exception as exc:
            logger.error("[%s] send_document failed to=%s: %s", self.name, _safe_id(chat_id), exc)
            return SendResult(success=False, error=str(exc))

    async def send_video(
        self,
        chat_id: str,
        video_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._send_session or not self._token:
            return SendResult(success=False, error="Not connected")
        try:
            message_id = await self._send_file(chat_id, video_path, caption or "")
            return SendResult(success=True, message_id=message_id)
        except Exception as exc:
            logger.error("[%s] send_video failed to=%s: %s", self.name, _safe_id(chat_id), exc)
            return SendResult(success=False, error=str(exc))

    async def send_voice(
        self,
        chat_id: str,
        audio_path: str,
        caption: Optional[str] = None,
        reply_to: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> SendResult:
        if not self._send_session or not self._token:
            return SendResult(success=False, error="Not connected")

        # Native outbound WeChat voice bubbles are not proven-working in the
        # upstream reference implementation. Prefer a reliable file attachment
        # fallback so users at least receive playable audio, even for .silk.
        fallback_caption = caption or "[voice message as attachment]"
        try:
            message_id = await self._send_file(
                chat_id,
                audio_path,
                fallback_caption,
                force_file_attachment=True,
            )
            return SendResult(success=True, message_id=message_id)
        except Exception as exc:
            logger.error("[%s] send_voice failed to=%s: %s", self.name, _safe_id(chat_id), exc)
            return SendResult(success=False, error=str(exc))

    async def _download_remote_media(self, url: str) -> str:
        from tools.url_safety import is_safe_url

        if not is_safe_url(url):
            raise ValueError(f"Blocked unsafe URL (SSRF protection): {url}")

        assert self._send_session is not None
        # Use asyncio.wait_for() instead of aiohttp ClientTimeout to avoid
        # "Timeout context manager should be used inside a task" errors.
        async def _do_fetch():
            async with self._send_session.get(url) as response:
                response.raise_for_status()
                return await response.read()
        data = await asyncio.wait_for(_do_fetch(), timeout=30)
        suffix = Path(url.split("?", 1)[0]).suffix or ".bin"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
            handle.write(data)
            return handle.name

    async def _send_file(
        self,
        chat_id: str,
        path: str,
        caption: str,
        force_file_attachment: bool = False,
    ) -> str:
        # R1-4a: thin orchestrator — delegates CDN upload + envelope
        # dispatch to 2 phase functions in ``wechat_ilink_phases.py``.
        from butler.gateway.platforms.wechat_ilink_phases import (
            _phase_file_dispatch_message,
            _phase_file_request_upload,
        )

        assert self._send_session is not None and self._token is not None
        plaintext = Path(path).read_bytes()
        media_type, item_builder = self._outbound_media_builder(
            path, force_file_attachment=force_file_attachment,
        )
        filekey = secrets.token_hex(16)
        aes_key = secrets.token_bytes(16)
        rawsize = len(plaintext)
        rawfilemd5 = hashlib.md5(plaintext).hexdigest()
        _upload_url, encrypted_query_param, ciphertext = await _phase_file_request_upload(
            self, chat_id=chat_id, media_type=media_type,
            filekey=filekey, aes_key=aes_key, plaintext=plaintext,
            rawsize=rawsize, rawfilemd5=rawfilemd5,
            filesize=_aes_padded_size(rawsize),
        )
        context_token = self._token_store.get(self._account_id, chat_id)
        media_item = self._build_outbound_media_item(
            path, media_type, item_builder,
            encrypted_query_param=encrypted_query_param,
            aes_key=aes_key,
            ciphertext_size=len(ciphertext),
            plaintext_size=rawsize,
            rawfilemd5=rawfilemd5,
        )
        return _phase_file_dispatch_message(
            self, chat_id=chat_id, media_item=media_item,
            caption=caption, context_token=context_token,
        )

    def _build_outbound_media_item(
        self,
        path: str,
        media_type: int,
        item_builder: Any,
        *,
        encrypted_query_param: str,
        aes_key: bytes,
        ciphertext_size: int,
        plaintext_size: int,
        rawfilemd5: str,
    ) -> Dict[str, Any]:
        """Assemble kwargs for the per-mime item builder; add silk voice metadata.

        The iLink API expects ``aes_key`` as ``base64(hex_string)``,
        not ``base64(raw_bytes)`` — sending the latter produces grey
        boxes on the receiver side because the decryption key doesn't
        match.
        """
        aes_key_for_api = base64.b64encode(aes_key.hex().encode("ascii")).decode("ascii")
        item_kwargs: Dict[str, Any] = {
            "encrypt_query_param": encrypted_query_param,
            "aes_key_for_api": aes_key_for_api,
            "ciphertext_size": ciphertext_size,
            "plaintext_size": plaintext_size,
            "filename": Path(path).name,
            "rawfilemd5": rawfilemd5,
        }
        if media_type == MEDIA_VOICE and path.endswith(".silk"):
            item_kwargs["encode_type"] = 6
            item_kwargs["sample_rate"] = 24000
            item_kwargs["bits_per_sample"] = 16
        return item_builder(**item_kwargs)
        return _phase_file_dispatch_message(
            self,
            chat_id=chat_id,
            media_item=media_item,
            caption=caption,
            context_token=context_token,
        )

    def _outbound_media_builder(self, path: str, force_file_attachment: bool = False):
        # R1-4a: thin orchestrator — guess MIME, then delegate to a
        # per-mime builder factory in ``wechat_ilink_phases.py``. The
        # 5-line dispatch table replaces the original 68L body.
        import mimetypes

        from butler.gateway.platforms.wechat_ilink_phases import (
            _build_audio_item,
            _build_file_item,
            _build_image_item,
            _build_video_item,
            _build_voice_item,
        )

        mime = mimetypes.guess_type(path)[0] or "application/octet-stream"
        if mime.startswith("image/"):
            return MEDIA_IMAGE, _build_image_item
        if mime.startswith("video/"):
            return MEDIA_VIDEO, _build_video_item
        if path.endswith(".silk") and not force_file_attachment:
            return MEDIA_VOICE, _build_voice_item
        if mime.startswith("audio/"):
            return MEDIA_FILE, _build_audio_item
        return MEDIA_FILE, _build_file_item

    async def get_chat_info(self, chat_id: str) -> Dict[str, Any]:
        chat_type = "group" if chat_id.endswith("@chatroom") else "dm"
        return {"name": chat_id, "type": chat_type, "chat_id": chat_id}

    def extract_local_files(self, content: str) -> tuple[list[str], str]:
        from butler.gateway.outbound_files import extract_deliverable_local_files

        paths, cleaned = extract_deliverable_local_files(content)
        return paths, cleaned

    def format_message(self, content: Optional[str]) -> str:
        if content is None:
            return ""
        from butler.gateway.pii_scrub import scrub_outbound_text

        scrubbed = scrub_outbound_text(str(content))
        return _wrap_copy_friendly_lines_for_wechat(_normalize_markdown_blocks(scrubbed))


async def send_wechat_direct(
    *,
    extra: Dict[str, Any],
    token: Optional[str],
    chat_id: str,
    message: str,
    media_files: Optional[List[Tuple[str, bool]]] = None,
) -> Dict[str, Any]:
    """
    One-shot send helper for ``send_message`` and cron delivery.

    This bypasses the long-poll adapter lifecycle and uses the raw API directly.
    """
    # R1-4b: thin orchestrator. Credential resolution lives in
    # ``_phase_direct_resolve_credentials``; the two delivery paths
    # (live-adapter fast path vs fresh-adapter one-shot) live in
    # ``wechat_ilink_direct.py``.
    from butler.gateway.platforms.wechat_ilink_direct import (
        _phase_direct_resolve_credentials,
        _phase_direct_send_via_fresh_adapter,
        _phase_direct_send_via_live_adapter,
    )

    creds = _phase_direct_resolve_credentials(extra, token)
    if "error" in creds:
        return creds
    resolved_token = creds["token"]
    account_id = creds["account_id"]

    token_store = ContextTokenStore(str(get_butler_home()))
    token_store.restore(account_id)
    context_token = token_store.get(account_id, chat_id)

    live_adapter = _ADAPTER_REGISTRY.get(resolved_token)
    send_session = getattr(live_adapter, "_send_session", None)
    if (live_adapter is not None and send_session is not None
            and not send_session.closed
            and send_session._loop is asyncio.get_running_loop()):
        return await _phase_direct_send_via_live_adapter(
            live_adapter,
            chat_id=chat_id,
            message=message,
            media_files=media_files,
            context_token=context_token,
        )
    return await _phase_direct_send_via_fresh_adapter(
        creds=creds,
        chat_id=chat_id,
        message=message,
        media_files=media_files,
        context_token=context_token,
        token_store=token_store,
    )
