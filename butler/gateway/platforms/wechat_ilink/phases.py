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
size contract, enforced by ``tests/gateway/test_wechat_ilink_split.py``).
"""

from __future__ import annotations

import hashlib
import logging
import os
from datetime import datetime
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

from butler.gateway.platforms.types import MessageEvent

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Carrier + outbound send sub-phases (ENG-5: send_phases.py)
# ---------------------------------------------------------------------------

from butler.gateway.platforms.wechat_ilink.send_phases import (  # noqa: E402
    WeChatSendState,
    _build_audio_item,
    _build_file_item,
    _build_image_item,
    _build_video_item,
    _build_voice_item,
    _phase_chunk_attempt,
    _phase_chunk_handle_response,
    _phase_file_dispatch_message,
    _phase_file_request_upload,
    _phase_send_attachments,
    _phase_send_text_chunks,
    _resolve_upload_url,
    _send_caption_first,
    _send_media_envelope,
)


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
# connect sub-phases (ENG-5: butler.gateway.platforms.wechat_ilink.connect_phases)
# ===========================================================================

from butler.gateway.platforms.wechat_ilink.connect_phases import (  # noqa: E402
    _acquire_token_lock,
    _open_aiohttp_sessions,
    _phase_connect_open_sessions,
    _phase_connect_validate,
    _start_poll_and_register,
    _warn_group_policy_limitation,
)


# poll sub-phase (ENG-5: poll_phases.py)
from butler.gateway.platforms.wechat_ilink.poll_phases import (  # noqa: E402
    _phase_poll_handle_response,
)


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


# QR-login sub-phases (ENG-5: qr_phases.py)
from butler.gateway.platforms.wechat_ilink.qr_phases import (  # noqa: E402
    QrLoginState,
    _phase_qr_finalize,
    _phase_qr_poll_iteration,
    _phase_qr_poll_step,
    _phase_qr_refresh,
    _phase_qr_render,
    _phase_qr_request_code,
    _qr_handle_expired,
)


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
