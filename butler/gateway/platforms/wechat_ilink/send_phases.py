"""WeChat outbound send sub-phases (ENG-5 — extracted from phases.py)."""

from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, cast

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

logger = logging.getLogger(__name__)


@dataclass
class WeChatSendState:
    """Mutable carrier for one text-chunk send attempt.

    Phases mutate fields on this object. The orchestrator initializes
    the latch in ``_send_text_chunk`` and reads final status after
    the last attempt.
    """

    # ``retried_without_token`` — at most one tokenless retry per chunk.
    retried_without_token: bool = False
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

    return cast(
        Dict[str, Any],
        await _send_message(
            adapter._send_session,
            base_url=adapter._base_url,
            token=adapter._token,
            to=chat_id,
            text=chunk,
            context_token=context_token,
            client_id=client_id,
        ),
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
    if not isinstance(resp, dict):
        return (
            "raise",
            context_token,
            RuntimeError(f"iLink sendmessage returned non-dict: {type(resp).__name__}"),
        )
    if not resp:
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
    from butler.gateway.platforms.wechat_ilink.send_phases_ops import deliver_attachment_safe

    for media_path, is_voice in media_files:
        await deliver_attachment_safe(
            adapter,
            path=media_path,
            is_voice=is_voice,
            chat_id=chat_id,
            metadata=metadata,
        )
    for file_path in local_files:
        await deliver_attachment_safe(
            adapter,
            path=file_path,
            is_voice=False,
            chat_id=chat_id,
            metadata=metadata,
        )


async def _phase_send_text_chunks(
    adapter: "WeChatAdapter",
    final_content: str,
    chat_id: str,
    context_token: Optional[str],
    *,
    metadata: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    """Phase S2: split + deliver the text portion of a send.

    Returns the last ``client_id`` (mirroring the original ``send``
    return) so the host can build a ``SendResult(message_id=...)``.
    Inter-chunk delay uses ``butler.gateway.outbound_delay`` to honor
    per-session override + default fallback.
    """
    from butler.gateway.outbound_delay import inter_chunk_delay_seconds

    formatted = adapter.format_message(final_content)
    chunks = [
        c for c in adapter._split_text(formatted, metadata=metadata) if c and c.strip()
    ]
    if not chunks and (final_content or "").strip():
        logger.warning(
            "[%s] outbound text empty after format/split (raw_len=%d formatted_len=%d)",
            adapter.name,
            len(final_content or ""),
            len(formatted or ""),
        )
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
        return str(_cdn_upload_url(adapter._cdn_base_url, upload_param, filekey))
    raise RuntimeError(
        f"getUploadUrl returned neither upload_param nor upload_full_url: {upload_response}"
    )


async def _phase_file_dispatch_message(
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
        await _send_caption_first(adapter, chat_id, caption, context_token)
    return await _send_media_envelope(adapter, chat_id, media_item, context_token)


async def _send_caption_first(
    adapter: "WeChatAdapter",
    chat_id: str,
    caption: str,
    context_token: Optional[str],
) -> None:
    """Dispatch a separate text message for the caption (client_id discarded)."""
    from butler.gateway.platforms.wechat_ilink import _send_message

    await _send_message(
        adapter._send_session,
        base_url=adapter._base_url,
        token=adapter._token,
        to=chat_id,
        text=adapter.format_message(caption),
        context_token=context_token,
        client_id=f"hermes-wechat-{uuid.uuid4().hex}",
    )


async def _send_media_envelope(
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
    await _api_post(
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


__all__ = [
    "WeChatSendState",
    "_classify_chunk_error",
    "_build_audio_item",
    "_build_file_item",
    "_build_image_item",
    "_build_video_item",
    "_build_voice_item",
    "_phase_chunk_attempt",
    "_phase_chunk_handle_response",
    "_phase_file_dispatch_message",
    "_phase_file_request_upload",
    "_phase_send_attachments",
    "_phase_send_text_chunks",
    "_resolve_upload_url",
    "_send_caption_first",
    "_send_media_envelope",
]
