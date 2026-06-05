"""Phase helpers extracted from ``WeChatAdapter`` (R1-4a split).

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-4a

The original ``WeChatAdapter`` class (L506-1509 in
``wechat_ilink.py``, ~1005 lines) had 9 god methods over the 50L cap:

* ``__init__`` (53L)
* ``connect`` (51L)
* ``_poll_loop`` (70L)
* ``_process_message`` (69L)
* ``_send_text_chunk`` (111L)
* ``send`` (63L)
* ``_send_file`` (93L)
* ``_outbound_media_builder`` (68L)

Per the audit's recommendation, this module mirrors the R1-6 / R1-8
phase pattern:

* :func:`_phase_init_account` / :func:`_phase_init_chunks` /
  :func:`_phase_init_policies` / :func:`_phase_init_dedup` —
  ``__init__`` sub-phases.
* :func:`_phase_connect_validate` / :func:`_phase_connect_open_sessions` —
  ``connect`` sub-phases.
* :func:`_phase_poll_handle_response` — single-poll-iteration response
  handling (status / backoff / dedup-buf / message dispatch).
* :func:`_phase_inbound_dedup` / :func:`_phase_inbound_chat_policy` /
  :func:`_phase_inbound_build_event` — ``_process_message`` sub-phases.
* :func:`_phase_chunk_attempt` / :func:`_phase_chunk_handle_response` —
  ``_send_text_chunk`` sub-phases, sharing :class:`WeChatSendState`.
* :func:`_phase_send_attachments` / :func:`_phase_send_text_chunks` —
  ``send`` sub-phases.
* :func:`_phase_file_request_upload` / :func:`_phase_file_dispatch_message` —
  ``_send_file`` sub-phases.
* :func:`_build_image_item` / :func:`_build_video_item` /
  :func:`_build_voice_item` / :func:`_build_audio_item` /
  :func:`_build_file_item` — ``_outbound_media_builder`` per-mime
  factories (the host method is a 5-line dispatch).

A mutable :class:`WeChatSendState` carrier threads per-send-chunk state
between phases — the ``retried_without_token`` latch, in particular, is
shared between ``_phase_chunk_attempt`` and ``_phase_chunk_handle_response``.

R1-4b extends this module with the QR-login phase functions
(:func:`_phase_qr_request_code` / :func:`_phase_qr_render` /
:func:`_phase_qr_poll_iteration` / :func:`_phase_qr_refresh` /
:func:`_phase_qr_finalize`) plus the :class:`QrLoginState` carrier.
The host ``qr_login`` function in ``wechat_ilink.py`` delegates to
these phases and stays a thin state-machine < 50 source lines.

Each phase helper is a thin orchestrator (< 50 source lines, R1-5.2
size contract, enforced by ``tests/test_wechat_ilink_split.py``).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from butler.gateway.platforms.types import MessageEvent

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Carrier — mutable per-send-chunk state shared between phases.
# ---------------------------------------------------------------------------

@dataclass
class WeChatSendState:
    """Mutable carrier for one text-chunk send attempt.

    Phases mutate fields on this object. The orchestrator initializes
    the latch in ``_send_text_chunk`` and reads final status after
    the last attempt.
    """

    # ``retried_without_token`` — at most one tokenless retry per chunk.
    retried_without_token: bool = False


# ===========================================================================
# __init__ sub-phases (4 of them) — keep each < 50L.
# ===========================================================================

def _phase_init_account(
    adapter: "WeChatAdapter", config: Any,
) -> None:
    """Phase I1: resolve token / base_url / account_id / cdn_base_url.

    Reads from ``config.extra`` and the ``WECHAT_*`` env vars. If the
    account id was provided without a token, the on-disk persisted
    credential is loaded as a fallback.
    """
    from butler.gateway.platforms.wechat_ilink import (
        ILINK_BASE_URL,
        WECHAT_CDN_BASE_URL,
        load_wechat_account,
    )

    extra = config.extra or {}
    data_home = str(adapter._data_home)
    adapter._account_id = str(
        extra.get("account_id") or os.getenv("WECHAT_ACCOUNT_ID", "")
    ).strip()
    adapter._token = str(
        config.token or extra.get("token") or os.getenv("WECHAT_TOKEN", "")
    ).strip()
    adapter._base_url = str(
        extra.get("base_url") or os.getenv("WECHAT_BASE_URL", ILINK_BASE_URL)
    ).strip().rstrip("/")
    adapter._cdn_base_url = str(
        extra.get("cdn_base_url") or os.getenv("WECHAT_CDN_BASE_URL", WECHAT_CDN_BASE_URL)
    ).strip().rstrip("/")

    if adapter._account_id and not adapter._token:
        persisted = load_wechat_account(data_home, adapter._account_id)
        if persisted:
            adapter._token = str(persisted.get("token") or "").strip()
            adapter._base_url = (
                str(persisted.get("base_url") or adapter._base_url).strip().rstrip("/")
            )


def _phase_init_chunks(adapter: "WeChatAdapter", config: Any) -> None:
    """Phase I2: resolve chunk delay / retry policy from config + env."""
    extra = config.extra or {}
    adapter._send_chunk_delay_seconds = float(
        extra.get("send_chunk_delay_seconds")
        or os.getenv("WECHAT_SEND_CHUNK_DELAY_SECONDS", "1.5")
    )
    adapter._send_chunk_retries = int(
        extra.get("send_chunk_retries") or os.getenv("WECHAT_SEND_CHUNK_RETRIES", "4")
    )
    adapter._send_chunk_retry_delay_seconds = float(
        extra.get("send_chunk_retry_delay_seconds")
        or os.getenv("WECHAT_SEND_CHUNK_RETRY_DELAY_SECONDS", "1.0")
    )


def _phase_init_policies(adapter: "WeChatAdapter", config: Any) -> None:
    """Phase I3: resolve DM / group policies + allowlists."""
    from butler.gateway.platforms.wechat_ilink import _coerce_bool

    extra = config.extra or {}
    adapter._dm_policy = str(
        extra.get("dm_policy") or os.getenv("WECHAT_DM_POLICY", "open")
    ).strip().lower()
    adapter._group_policy = str(
        extra.get("group_policy") or os.getenv("WECHAT_GROUP_POLICY", "disabled")
    ).strip().lower()
    allow_from = extra.get("allow_from")
    if allow_from is None:
        allow_from = os.getenv("WECHAT_ALLOWED_USERS", "")
    group_allow_from = extra.get("group_allow_from")
    if group_allow_from is None:
        group_allow_from = os.getenv("WECHAT_GROUP_ALLOWED_USERS", "")
    adapter._allow_from = adapter._coerce_list(allow_from)
    adapter._group_allow_from = adapter._coerce_list(group_allow_from)
    adapter._split_multiline_messages = _coerce_bool(
        extra.get("split_multiline_messages")
        or os.getenv("WECHAT_SPLIT_MULTILINE_MESSAGES"),
        default=False,
    )


def _phase_init_dedup(adapter: "WeChatAdapter") -> None:
    """Phase I4: create the message-id + content-fingerprint dedups.

    Separated from ``_phase_init_account`` so the imports stay clean
    and the dedup TTLs are configurable independently of credentials.
    """
    from butler.gateway.platforms.helpers import MessageDeduplicator
    from butler.gateway.platforms.wechat_ilink import (
        _content_dedup_ttl,
        _message_id_dedup_ttl,
    )

    adapter._id_dedup = MessageDeduplicator(ttl_seconds=_message_id_dedup_ttl())
    adapter._content_dedup = MessageDeduplicator(ttl_seconds=_content_dedup_ttl())


# ===========================================================================
# connect sub-phases
# ===========================================================================

def _phase_connect_validate(adapter: "WeChatAdapter") -> bool:
    """Phase C1: validate runtime deps + token + account_id.

    Returns True if validation passed; False if any fatal error was set.
    """
    from butler.gateway.platforms.wechat_ilink import check_wechat_requirements

    if not check_wechat_requirements():
        message = "WeChat startup failed: aiohttp and cryptography are required"
        adapter._set_fatal_error("wechat_missing_dependency", message, retryable=False)
        logger.warning("[%s] %s", adapter.name, message)
        return False
    if not adapter._token:
        message = "WeChat startup failed: WECHAT_TOKEN is required"
        adapter._set_fatal_error("wechat_missing_token", message, retryable=False)
        logger.warning("[%s] %s", adapter.name, message)
        return False
    if not adapter._account_id:
        message = "WeChat startup failed: WECHAT_ACCOUNT_ID is required"
        adapter._set_fatal_error("wechat_missing_account", message, retryable=False)
        logger.warning("[%s] %s", adapter.name, message)
        return False
    return True


def _phase_connect_open_sessions(adapter: "WeChatAdapter") -> None:
    """Phase C2: acquire lock, open poll/send sessions, register, mark connected.

    Caller has already validated deps + token + account_id. We disable
    aiohttp's built-in ClientTimeout on the send session (managed
    externally via ``asyncio.wait_for``) to avoid the "Timeout context
    manager should be used inside a task" error when ``send()`` is
    invoked via ``asyncio.run_coroutine_threadsafe`` from cron.
    """
    if not _acquire_token_lock(adapter):
        return
    _open_aiohttp_sessions(adapter)
    _start_poll_and_register(adapter)


def _acquire_token_lock(adapter: "WeChatAdapter") -> bool:
    """Acquire the platform-wide bot-token lock (best-effort)."""
    try:
        return bool(adapter._acquire_platform_lock(
            "wechat-bot-token", adapter._token, "WeChat bot token",
        ))
    except Exception as exc:
        logger.debug(
            "[%s] Token lock unavailable (non-fatal): %s", adapter.name, exc,
        )
        return True  # treat as "proceed"


def _open_aiohttp_sessions(adapter: "WeChatAdapter") -> None:
    """Open the poll + send aiohttp sessions (no built-in timeout)."""
    import aiohttp

    from butler.gateway.platforms.wechat_ilink import _make_ssl_connector

    connector = _make_ssl_connector()
    adapter._poll_session = aiohttp.ClientSession(trust_env=True, connector=connector)
    adapter._send_session = aiohttp.ClientSession(
        trust_env=True,
        connector=connector,
        timeout=aiohttp.ClientTimeout(
            total=None, connect=None, sock_connect=None, sock_read=None
        ),
    )


def _start_poll_and_register(adapter: "WeChatAdapter") -> None:
    """Restore token store, start poll task, mark connected, register."""
    from butler.gateway.platforms.wechat_ilink import (
        _LIVE_ADAPTERS,
        _safe_id,
    )

    adapter._token_store.restore(adapter._account_id)
    adapter._poll_task = asyncio.create_task(adapter._poll_loop(), name="wechat-poll")
    adapter._mark_connected()
    _LIVE_ADAPTERS[adapter._token] = adapter
    logger.info(
        "[%s] Connected account=%s base=%s",
        adapter.name, _safe_id(adapter._account_id), adapter._base_url,
    )
    if adapter._group_policy != "disabled":
        _warn_group_policy_limitation(adapter)


def _warn_group_policy_limitation(adapter: "WeChatAdapter") -> None:
    """Log a one-shot warning when group_policy != 'disabled'.

    iLink bot identities can't join ordinary WeChat groups; we tell
    the operator so the silent-no-events outcome is at least expected.
    """
    logger.warning(
        "[%s] WECHAT_GROUP_POLICY=%s is set, but QR-login connects an iLink bot "
        "identity (e.g. ...@im.bot) which typically cannot be invited into ordinary "
        "WeChat groups. iLink usually does not deliver ordinary-group events for "
        "these accounts, so group messages may never reach Hermes regardless of this "
        "policy. If group delivery doesn't work, the limitation is on the iLink side, "
        "not in Hermes.",
        adapter.name, adapter._group_policy,
    )


# ===========================================================================
# _poll_loop sub-phase
# ===========================================================================

def _phase_poll_handle_response(
    adapter: "WeChatAdapter",
    response: Dict[str, Any],
) -> Tuple[str, List[Dict[str, Any]]]:
    """Phase P1: classify a single ``getUpdates`` response.

    Returns ``(signal, messages_to_dispatch)``. ``signal`` is one of:

    * ``"ok"`` — normal, caller should process ``messages``.
    * ``"session_expired"`` — sleep 10 minutes + continue.

    Side effect: persists the new sync_buf to disk when present.
    """
    from butler.gateway.platforms.wechat_ilink import (
        SESSION_EXPIRED_ERRCODE,
        _is_stale_session_ret,
        _save_sync_buf,
    )

    ret = response.get("ret", 0)
    errcode = response.get("errcode", 0)
    if ret not in (0, None) or errcode not in (0, None):
        if (ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE
                or _is_stale_session_ret(ret, errcode, response.get("errmsg"))):
            logger.error("[%s] Session expired; pausing for 10 minutes", adapter.name)
            return ("session_expired", [])

    new_sync_buf = str(response.get("get_updates_buf") or "")
    if new_sync_buf:
        _save_sync_buf(adapter._data_home, adapter._account_id, new_sync_buf)
    return ("ok", list(response.get("msgs") or []))


# ===========================================================================
# _process_message sub-phases
# ===========================================================================

def _phase_inbound_dedup(
    adapter: "WeChatAdapter",
    message: Dict[str, Any],
    sender_id: str,
    text: str,
) -> bool:
    """Phase M1: short-circuit if message is a duplicate.

    Returns True if processing should CONTINUE; False if the message
    should be silently dropped. Two layers of dedup:

    * message_id (300s TTL) — iLink's own dedup should already handle
      this, but a slow path can still re-deliver after a reconnect.
    * content fingerprint (20s TTL) — catches iLink duplicate
      deliveries of the same text within a short window.
    """
    from butler.gateway.platforms.wechat_ilink import _content_dedup_ttl

    message_id = str(message.get("message_id") or "").strip()
    if message_id and adapter._id_dedup.is_duplicate(message_id):
        return False
    if text:
        content_key = f"content:{sender_id}:{hashlib.md5(text.encode()).hexdigest()}"
        if adapter._content_dedup.is_duplicate(content_key):
            logger.info(
                "[%s] Content-dedup: skipping duplicate text from %s (same body within %.0fs)",
                adapter.name, sender_id, _content_dedup_ttl(),
            )
            return False
    return True


def _phase_inbound_chat_policy(
    adapter: "WeChatAdapter",
    chat_type: str,
    effective_chat_id: str,
    sender_id: str,
) -> bool:
    """Phase M2: apply group / DM policy + allowlist.

    Returns True if processing should CONTINUE; False if the message
    should be silently dropped.
    """
    if chat_type == "group":
        if adapter._group_policy == "disabled":
            return False
        if (adapter._group_policy == "allowlist"
                and effective_chat_id not in adapter._group_allow_from):
            return False
    elif not adapter._is_dm_allowed(sender_id):
        return False
    return True


def _phase_inbound_build_event(
    adapter: "WeChatAdapter",
    message: Dict[str, Any],
    sender_id: str,
    text: str,
    media_paths: List[str],
    media_types: List[str],
    effective_chat_id: str,
    chat_type: str,
    message_id: str,
) -> MessageEvent:
    """Phase M3: build the MessageEvent + emit log line.

    Caller has already run dedup + chat-policy + media collection.
    This phase is a pure constructor for the inbound event.
    """
    from butler.gateway.platforms.wechat_ilink import (
        _message_type_from_media,
        _safe_id,
    )

    source = adapter.build_source(
        chat_id=effective_chat_id,
        chat_type=chat_type,
        user_id=sender_id,
        user_name=sender_id,
    )
    event = MessageEvent(
        text=text,
        message_type=_message_type_from_media(media_types, text),
        source=source,
        raw_message=message,
        message_id=message_id or None,
        media_urls=media_paths,
        media_types=media_types,
        timestamp=datetime.now(),
    )
    logger.info(
        "[%s] inbound from=%s type=%s media=%d",
        adapter.name, _safe_id(sender_id), source.chat_type, len(media_paths),
    )
    return event


# ===========================================================================
# _send_text_chunk sub-phases
# ===========================================================================

async def _phase_chunk_attempt(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    chunk: str,
    context_token: Optional[str],
    client_id: str,
) -> Dict[str, Any]:
    """Phase C1: perform one ``_send_message`` API call.

    Raises whatever exception the transport raises (caller catches +
    backoffs); returns the iLink response dict on a clean HTTP roundtrip.
    """
    from butler.gateway.platforms.wechat_ilink import _send_message

    return _send_message(  # type: ignore[return-value]
        adapter._send_session,
        base_url=adapter._base_url,
        token=adapter._token,
        to=chat_id,
        text=chunk,
        context_token=context_token,
        client_id=client_id,
    )


def _phase_chunk_handle_response(
    adapter: "WeChatAdapter",
    resp: Optional[Dict[str, Any]],
    *,
    chat_id: str,
    context_token: Optional[str],
    state: WeChatSendState,
) -> Tuple[str, Optional[str], Optional[Exception]]:
    """Phase C2: classify one iLink response.

    Returns ``(action, new_context_token, last_error)`` where ``action``
    is one of:

    * ``"ok"`` — chunk delivered, caller can return.
    * ``"retry_without_token"`` — caller should ``continue`` and
      re-send the same chunk with ``context_token=None``.
    * ``"retry"`` — caller should backoff + ``continue`` the loop.
    * ``"raise"`` — caller should ``raise last_error`` (already built).
    """
    if not resp or not isinstance(resp, dict):
        return ("ok", context_token, None)
    ret, errcode = resp.get("ret"), resp.get("errcode")
    if ret in (0, None) and errcode in (0, None):
        return ("ok", context_token, None)
    return _classify_chunk_error(adapter, resp, ret, errcode, chat_id, context_token, state)


def _classify_chunk_error(
    adapter: "WeChatAdapter",
    resp: Dict[str, Any],
    ret: Any,
    errcode: Any,
    chat_id: str,
    context_token: Optional[str],
    state: WeChatSendState,
) -> Tuple[str, Optional[str], Optional[Exception]]:
    """Apply the (session_expired / rate_limit / other) decision tree."""
    from butler.gateway.platforms.wechat_ilink import (
        RATE_LIMIT_ERRCODE,
        SESSION_EXPIRED_ERRCODE,
        _is_stale_session_ret,
        _safe_id,
    )

    if (ret == SESSION_EXPIRED_ERRCODE or errcode == SESSION_EXPIRED_ERRCODE
            or _is_stale_session_ret(ret, errcode, resp.get("errmsg"))):
        if not state.retried_without_token and context_token:
            state.retried_without_token = True
            adapter._token_store._cache.pop(
                adapter._token_store._key(adapter._account_id, chat_id), None,
            )
            logger.warning(
                "[%s] session expired for %s; retrying without context_token",
                adapter.name, _safe_id(chat_id),
            )
            return ("retry_without_token", None, None)
    if ret == RATE_LIMIT_ERRCODE or errcode == RATE_LIMIT_ERRCODE:
        errmsg = resp.get("errmsg") or resp.get("msg") or "rate limited"
        return (
            "retry", context_token,
            RuntimeError(
                f"iLink sendmessage rate limited: ret={ret} errcode={errcode} errmsg={errmsg}"
            ),
        )
    errmsg = resp.get("errmsg") or resp.get("msg") or "unknown error"
    return (
        "raise", context_token,
        RuntimeError(
            f"iLink sendmessage error: ret={ret} errcode={errcode} errmsg={errmsg}"
        ),
    )


# ===========================================================================
# send sub-phases
# ===========================================================================

async def _phase_send_attachments(
    adapter: "WeChatAdapter",
    media_files: List[Tuple[str, bool]],
    local_files: List[str],
    chat_id: str,
    metadata: Optional[Dict[str, Any]],
) -> None:
    """Phase S1: deliver extracted MEDIA: tags + bare local file paths.

    MEDIA entries come with an ``is_voice`` flag; bare paths are treated
    as non-voice. The per-extension dispatch table is local; failures
    are logged + swallowed (matching the original ``send`` semantics).
    """
    _AUDIO_EXTS = {".ogg", ".opus", ".mp3", ".wav", ".m4a", ".flac"}
    _VIDEO_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".3gp"}
    _IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".gif"}

    async def _deliver(path: str, is_voice: bool) -> None:
        ext = Path(path).suffix.lower()
        if is_voice or ext in _AUDIO_EXTS:
            await adapter.send_voice(chat_id=chat_id, audio_path=path, metadata=metadata)
        elif ext in _VIDEO_EXTS:
            await adapter.send_video(chat_id=chat_id, video_path=path, metadata=metadata)
        elif ext in _IMAGE_EXTS:
            await adapter.send_image_file(chat_id=chat_id, image_path=path, metadata=metadata)
        else:
            await adapter.send_document(chat_id=chat_id, file_path=path, metadata=metadata)

    for media_path, is_voice in media_files:
        try:
            await _deliver(media_path, is_voice)
        except Exception as exc:
            logger.warning(
                "[%s] media delivery failed for %s: %s",
                adapter.name, media_path, exc,
            )
    for file_path in local_files:
        try:
            await _deliver(file_path, False)
        except Exception as exc:
            logger.warning(
                "[%s] local file delivery failed for %s: %s",
                adapter.name, file_path, exc,
            )


async def _phase_send_text_chunks(
    adapter: "WeChatAdapter",
    final_content: str,
    chat_id: str,
    context_token: Optional[str],
) -> Optional[str]:
    """Phase S2: split + deliver the text portion of a send.

    Returns the last ``client_id`` (mirroring the original ``send``
    return) so the host can build a ``SendResult(message_id=...)``.
    Inter-chunk delay uses ``butler.gateway.outbound_delay`` to honor
    per-session override + default fallback.
    """
    from butler.gateway.outbound_delay import inter_chunk_delay_seconds

    chunks = [
        c for c in adapter._split_text(adapter.format_message(final_content))
        if c and c.strip()
    ]
    last_message_id: Optional[str] = None
    for idx, chunk in enumerate(chunks):
        client_id = f"hermes-wechat-{uuid.uuid4().hex}"
        await adapter._send_text_chunk(
            chat_id=chat_id,
            chunk=chunk,
            context_token=context_token,
            client_id=client_id,
        )
        last_message_id = client_id
        if idx < len(chunks) - 1:
            delay = inter_chunk_delay_seconds(
                fallback_seconds=adapter._send_chunk_delay_seconds,
            )
            if delay > 0:
                await asyncio.sleep(delay)
    return last_message_id


# ===========================================================================
# _send_file sub-phases
# ===========================================================================

async def _phase_file_request_upload(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    media_type: int,
    filekey: str,
    aes_key: bytes,
    plaintext: bytes,
    rawsize: int,
    rawfilemd5: str,
    filesize: int,
) -> Tuple[str, str, bytes]:
    """Phase F1: ``getuploadurl`` + encrypt + CDN upload.

    Returns ``(upload_url, encrypted_query_param, ciphertext)``.

    Prefers ``upload_full_url`` (direct CDN) and falls back to the
    constructed CDN URL from ``upload_param``. Raises ``RuntimeError``
    if the API returned neither.
    """
    upload_url = await _resolve_upload_url(
        adapter, chat_id=chat_id, media_type=media_type, filekey=filekey,
        rawsize=rawsize, rawfilemd5=rawfilemd5, filesize=filesize, aes_key=aes_key,
    )
    from butler.gateway.platforms.wechat_ilink import (
        _aes128_ecb_encrypt,
        _upload_ciphertext,
    )
    ciphertext = _aes128_ecb_encrypt(plaintext, aes_key)
    encrypted_query_param = await _upload_ciphertext(
        adapter._send_session, ciphertext=ciphertext, upload_url=upload_url,
    )
    return (upload_url, encrypted_query_param, ciphertext)


async def _resolve_upload_url(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    media_type: int,
    filekey: str,
    rawsize: int,
    rawfilemd5: str,
    filesize: int,
    aes_key: bytes,
) -> str:
    """Call ``getuploadurl`` and pick ``upload_full_url`` or fallback URL."""
    from butler.gateway.platforms.wechat_ilink import (
        _cdn_upload_url,
        _get_upload_url,
    )

    upload_response = await _get_upload_url(
        adapter._send_session,
        base_url=adapter._base_url,
        token=adapter._token,
        to_user_id=chat_id,
        media_type=media_type,
        filekey=filekey,
        rawsize=rawsize,
        rawfilemd5=rawfilemd5,
        filesize=filesize,
        aeskey_hex=aes_key.hex(),
    )
    upload_full_url = str(upload_response.get("upload_full_url") or "")
    if upload_full_url:
        return upload_full_url
    upload_param = str(upload_response.get("upload_param") or "")
    if upload_param:
        return _cdn_upload_url(adapter._cdn_base_url, upload_param, filekey)
    raise RuntimeError(
        f"getUploadUrl returned neither upload_param nor upload_full_url: {upload_response}"
    )


def _phase_file_dispatch_message(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    media_item: Dict[str, Any],
    caption: str,
    context_token: Optional[str],
) -> str:
    """Phase F2: send the (caption + media) message envelope.

    If ``caption`` is non-empty, a text message is dispatched first so
    the user sees the caption alongside the attachment. Then the
    actual media envelope is sent. Returns the ``client_id`` of the
    media envelope (matching the original behavior — the caption's
    client_id is intentionally discarded).
    """
    if caption:
        _send_caption_first(adapter, chat_id, caption, context_token)
    return _send_media_envelope(adapter, chat_id, media_item, context_token)


def _send_caption_first(
    adapter: "WeChatAdapter",
    chat_id: str,
    caption: str,
    context_token: Optional[str],
) -> None:
    """Dispatch a separate text message for the caption (client_id discarded)."""
    from butler.gateway.platforms.wechat_ilink import _send_message

    _send_message(
        adapter._send_session,
        base_url=adapter._base_url,
        token=adapter._token,
        to=chat_id,
        text=adapter.format_message(caption),
        context_token=context_token,
        client_id=f"hermes-wechat-{uuid.uuid4().hex}",
    )


def _send_media_envelope(
    adapter: "WeChatAdapter",
    chat_id: str,
    media_item: Dict[str, Any],
    context_token: Optional[str],
) -> str:
    """POST the media envelope to ``EP_SEND_MESSAGE``. Returns client_id."""
    from butler.gateway.platforms.wechat_ilink import (
        EP_SEND_MESSAGE,
        MSG_STATE_FINISH,
        MSG_TYPE_BOT,
        _api_post,
    )

    last_message_id = f"hermes-wechat-{uuid.uuid4().hex}"
    _api_post(
        adapter._send_session,
        base_url=adapter._base_url,
        endpoint=EP_SEND_MESSAGE,
        payload={
            "msg": {
                "from_user_id": "",
                "to_user_id": chat_id,
                "client_id": last_message_id,
                "message_type": MSG_TYPE_BOT,
                "message_state": MSG_STATE_FINISH,
                "item_list": [media_item],
                **({"context_token": context_token} if context_token else {}),
            }
        },
        token=adapter._token,
        timeout_ms=15000,
    )
    return last_message_id


# ===========================================================================
# _outbound_media_builder per-mime factories.
# ===========================================================================

def _build_image_item(**kw: Any) -> Dict[str, Any]:
    """Image item factory (image/* MIME)."""
    return {
        "type": 2,  # ITEM_IMAGE
        "image_item": {
            "media": {
                "encrypt_query_param": kw["encrypt_query_param"],
                "aes_key": kw["aes_key_for_api"],
                "encrypt_type": 1,
            },
            "mid_size": kw["ciphertext_size"],
        },
    }


def _build_video_item(**kw: Any) -> Dict[str, Any]:
    """Video item factory (video/* MIME)."""
    return {
        "type": 5,  # ITEM_VIDEO
        "video_item": {
            "media": {
                "encrypt_query_param": kw["encrypt_query_param"],
                "aes_key": kw["aes_key_for_api"],
                "encrypt_type": 1,
            },
            "video_size": kw["ciphertext_size"],
            "play_length": kw.get("play_length", 0),
            "video_md5": kw.get("rawfilemd5", ""),
        },
    }


def _build_voice_item(**kw: Any) -> Dict[str, Any]:
    """Voice item factory (.silk file)."""
    return {
        "type": 3,  # ITEM_VOICE
        "voice_item": {
            "media": {
                "encrypt_query_param": kw["encrypt_query_param"],
                "aes_key": kw["aes_key_for_api"],
                "encrypt_type": 1,
            },
            "encode_type": kw.get("encode_type"),
            "bits_per_sample": kw.get("bits_per_sample"),
            "sample_rate": kw.get("sample_rate"),
            "playtime": kw.get("playtime", 0),
        },
    }


def _build_audio_item(**kw: Any) -> Dict[str, Any]:
    """Audio item factory (audio/* MIME — non-silk, fallback to file)."""
    return {
        "type": 4,  # ITEM_FILE
        "file_item": {
            "media": {
                "encrypt_query_param": kw["encrypt_query_param"],
                "aes_key": kw["aes_key_for_api"],
                "encrypt_type": 1,
            },
            "file_name": kw["filename"],
            "len": str(kw["plaintext_size"]),
        },
    }


def _build_file_item(**kw: Any) -> Dict[str, Any]:
    """Generic file item factory (catch-all)."""
    return {
        "type": 4,  # ITEM_FILE
        "file_item": {
            "media": {
                "encrypt_query_param": kw["encrypt_query_param"],
                "aes_key": kw["aes_key_for_api"],
                "encrypt_type": 1,
            },
            "file_name": kw["filename"],
            "len": str(kw["plaintext_size"]),
        },
    }


# ===========================================================================
# R1-4b — qr_login (top-level) sub-phases.
# ===========================================================================

@dataclass
class QrLoginState:
    """Mutable carrier for the QR-login state machine.

    Phases mutate fields on this object. The host ``qr_login``
    function initializes the carrier at startup and threads it
    through every iteration of the poll loop. Mirrors the
    :class:`WeChatSendState` pattern from R1-4a / R1-8.
    """

    refresh_count: int = 0
    current_base_url: str = ""
    qrcode_value: str = ""
    qrcode_url: str = ""
    qr_scan_data: str = ""


async def _phase_qr_request_code(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    bot_type: str,
) -> Optional[Tuple[str, str, str]]:
    """Phase Q1: fetch the QR from iLink.

    Returns ``(qrcode_value, qrcode_url, qr_scan_data)`` on success
    or ``None`` on failure (logs the underlying exception). The
    full scannable liteapp URL is preferred over the raw hex token.
    """
    from butler.gateway.platforms.wechat_ilink import (
        EP_GET_BOT_QR,
        QR_TIMEOUT_MS,
        _api_get,
    )

    try:
        qr_resp = await _api_get(
            session,
            base_url=base_url,
            endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
            timeout_ms=QR_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.error("wechat: failed to fetch QR code: %s", exc)
        return None

    qrcode_value = str(qr_resp.get("qrcode") or "")
    qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
    if not qrcode_value:
        logger.error("wechat: QR response missing qrcode")
        return None
    # qrcode_url is the full scannable liteapp URL; qrcode_value is just the hex token.
    # WeChat needs to scan the full URL, not the raw hex string.
    qr_scan_data = qrcode_url if qrcode_url else qrcode_value
    return (qrcode_value, qrcode_url, qr_scan_data)


def _phase_qr_render(qrcode_url: str, qr_scan_data: str) -> None:
    """Phase Q2: print the QR code to the terminal.

    Always prints the full URL when available; falls back to ASCII
    QR via the ``qrcode`` package, swallowing rendering errors so
    the operator can still scan the URL line.
    """
    print("\n请使用微信扫描以下二维码：")
    if qrcode_url:
        print(qrcode_url)
    try:
        import qrcode

        qr = qrcode.QRCode()
        qr.add_data(qr_scan_data)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except Exception as _qr_exc:
        print(f"（终端二维码渲染失败: {_qr_exc}，请直接打开上面的二维码链接）")


async def _phase_qr_poll_iteration(
    session: "aiohttp.ClientSession",
    *,
    current_base_url: str,
    qrcode_value: str,
) -> Tuple[str, Any]:
    """Phase Q3: one poll iteration.

    Returns ``(status, payload)`` where status is one of:

    * ``"wait"`` — keep polling (also returned on transient errors).
    * ``"scaned"`` — user scanned; still awaiting confirm.
    * ``"redirect"`` — server moved to a new host (payload is host).
    * ``"expired"`` — QR expired; caller should refresh.
    * ``"confirmed"`` — login succeeded (payload is credentials dict).
    """
    from butler.gateway.platforms.wechat_ilink import (
        EP_GET_QR_STATUS,
        QR_TIMEOUT_MS,
        _api_get,
    )

    try:
        status_resp = await _api_get(
            session,
            base_url=current_base_url,
            endpoint=f"{EP_GET_QR_STATUS}?qrcode={qrcode_value}",
            timeout_ms=QR_TIMEOUT_MS,
        )
    except asyncio.TimeoutError:
        return ("wait", None)
    except Exception as exc:
        logger.warning("wechat: QR poll error: %s", exc)
        return ("wait", None)

    status = str(status_resp.get("status") or "wait")
    if status == "scaned_but_redirect":
        return ("redirect", str(status_resp.get("redirect_host") or ""))
    if status == "expired":
        return ("expired", None)
    if status == "confirmed":
        return ("confirmed", {
            "account_id": str(status_resp.get("ilink_bot_id") or ""),
            "token": str(status_resp.get("bot_token") or ""),
            "base_url": str(status_resp.get("baseurl") or ""),
            "user_id": str(status_resp.get("ilink_user_id") or ""),
        })
    if status == "scaned":
        return ("scaned", None)
    return ("wait", None)


async def _phase_qr_refresh(
    session: "aiohttp.ClientSession",
    *,
    base_url: str,
    bot_type: str,
) -> Optional[Tuple[str, str, str]]:
    """Phase Q4: refresh the QR after expiry.

    Returns ``(qrcode_value, qrcode_url, qr_scan_data)`` on success
    or ``None`` on failure (logs the underlying exception).
    """
    from butler.gateway.platforms.wechat_ilink import (
        EP_GET_BOT_QR,
        QR_TIMEOUT_MS,
        _api_get,
    )

    try:
        qr_resp = await _api_get(
            session,
            base_url=base_url,
            endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
            timeout_ms=QR_TIMEOUT_MS,
        )
    except Exception as exc:
        logger.error("wechat: QR refresh failed: %s", exc)
        return None
    qrcode_value = str(qr_resp.get("qrcode") or "")
    qrcode_url = str(qr_resp.get("qrcode_img_content") or "")
    qr_scan_data = qrcode_url if qrcode_url else qrcode_value
    return (qrcode_value, qrcode_url, qr_scan_data)


def _phase_qr_finalize(
    data_home: str,
    payload: Dict[str, str],
) -> Optional[Dict[str, str]]:
    """Phase Q5: persist credentials + return the public dict.

    Returns ``None`` if the credential payload was incomplete (logs
    an error); otherwise persists via ``save_wechat_account`` and
    returns a 4-key dict matching the original ``qr_login`` return
    contract (``account_id`` / ``token`` / ``base_url`` / ``user_id``).
    """
    from butler.gateway.platforms.wechat_ilink import (
        ILINK_BASE_URL,
        save_wechat_account,
    )

    account_id = str(payload.get("account_id") or "")
    token = str(payload.get("token") or "")
    base_url = str(payload.get("base_url") or ILINK_BASE_URL)
    user_id = str(payload.get("user_id") or "")
    if not account_id or not token:
        logger.error("wechat: QR confirmed but credential payload was incomplete")
        return None
    save_wechat_account(
        data_home,
        account_id=account_id,
        token=token,
        base_url=base_url,
        user_id=user_id,
    )
    print(f"\n微信连接成功，account_id={account_id}")
    return {
        "account_id": account_id,
        "token": token,
        "base_url": base_url,
        "user_id": user_id,
    }


async def _phase_qr_poll_step(
    session: "aiohttp.ClientSession",
    state: QrLoginState,
    *,
    bot_type: str,
) -> Tuple[str, Any]:
    """Phase Q6: one full poll-step (poll + dispatch + state mutation).

    Returns ``(action, data)`` where action is one of:

    * ``"continue"`` — keep polling (``data`` is unused).
    * ``"confirmed"`` — login succeeded (``data`` is credentials dict).
    * ``"giveup"`` — terminal failure (``data`` is unused).

    Mutates ``state`` in place for ``redirect`` (updates
    ``current_base_url``) and ``expired`` (increments
    ``refresh_count``, calls :func:`_phase_qr_refresh` +
    :func:`_phase_qr_render`). Centralizes the user-facing
    status messages so the host ``qr_login`` stays a thin loop.
    """
    status, payload = await _phase_qr_poll_iteration(
        session,
        current_base_url=state.current_base_url,
        qrcode_value=state.qrcode_value,
    )
    if status == "wait":
        print(".", end="", flush=True)
        return ("continue", None)
    if status == "scaned":
        print("\n已扫码，请在微信里确认...")
        return ("continue", None)
    if status == "redirect":
        if payload:
            state.current_base_url = f"https://{payload}"
        return ("continue", None)
    if status == "expired":
        return await _qr_handle_expired(session, state, bot_type=bot_type)
    if status == "confirmed":
        return ("confirmed", payload)
    return ("continue", None)


async def _qr_handle_expired(
    session: "aiohttp.ClientSession",
    state: QrLoginState,
    *,
    bot_type: str,
) -> Tuple[str, Any]:
    """Internal helper: handle the ``expired`` poll status.

    Extracted from :func:`_phase_qr_poll_step` to keep that phase
    under the 50-line cap. Increments ``state.refresh_count``,
    gives up after 3 attempts, otherwise fetches + renders a
    fresh QR.
    """
    from butler.gateway.platforms.wechat_ilink import ILINK_BASE_URL

    state.refresh_count += 1
    if state.refresh_count > 3:
        print("\n二维码多次过期，请重新执行登录。")
        return ("giveup", None)
    print(f"\n二维码已过期，正在刷新... ({state.refresh_count}/3)")
    refreshed = await _phase_qr_refresh(
        session, base_url=ILINK_BASE_URL, bot_type=bot_type,
    )
    if refreshed is None:
        return ("giveup", None)
    state.qrcode_value, state.qrcode_url, state.qr_scan_data = refreshed
    _phase_qr_render(state.qrcode_url, state.qr_scan_data)
    return ("continue", None)


__all__ = [
    "WeChatSendState",
    "QrLoginState",
    # init sub-phases
    "_phase_init_account",
    "_phase_init_chunks",
    "_phase_init_policies",
    "_phase_init_dedup",
    # connect sub-phases
    "_phase_connect_validate",
    "_phase_connect_open_sessions",
    # poll sub-phase
    "_phase_poll_handle_response",
    # process_message sub-phases
    "_phase_inbound_dedup",
    "_phase_inbound_chat_policy",
    "_phase_inbound_build_event",
    # send_text_chunk sub-phases
    "_phase_chunk_attempt",
    "_phase_chunk_handle_response",
    # send sub-phases
    "_phase_send_attachments",
    "_phase_send_text_chunks",
    # _send_file sub-phases
    "_phase_file_request_upload",
    "_phase_file_dispatch_message",
    # _outbound_media_builder per-mime factories
    "_build_image_item",
    "_build_video_item",
    "_build_voice_item",
    "_build_audio_item",
    "_build_file_item",
    # R1-4b qr_login sub-phases
    "_phase_qr_request_code",
    "_phase_qr_render",
    "_phase_qr_poll_iteration",
    "_phase_qr_refresh",
    "_phase_qr_finalize",
    "_phase_qr_poll_step",
]
