"""Phase helpers for the ``send_wechat_direct`` one-shot path (R1-4b).

Audit source: ``docs/reviews/project-deep-audit-2026-06-r1to8.md`` §R1-4b

The original top-level ``send_wechat_direct`` (L1307-1409 in
``wechat_ilink.py``, ~103L) had three concerns interleaved in
one function:

1. Resolve ``account_id`` / ``base_url`` / ``cdn_base_url`` /
   ``token`` from ``extra`` + ``WECHAT_*`` env vars.
2. Deliver the text + media via a live adapter (fast path) if one
   is registered for the same token in this event loop.
3. Otherwise build a one-shot ``WeChatAdapter`` and use it.

This module owns concerns 1-3 as small phase functions:

* :func:`_phase_direct_resolve_credentials` — read env/extra, return
  either a credentials dict or an error dict (mirrors the
  ``{"error": ...}`` return contract of the host).
* :func:`_phase_direct_send_via_live_adapter` — deliver via the
  live adapter registered in ``_ADAPTER_REGISTRY`` for the same token.
* :func:`_phase_direct_send_via_fresh_adapter` — build a fresh
  ``WeChatAdapter`` and deliver through it.

The host ``send_wechat_direct`` function in ``wechat_ilink.py``
becomes a thin orchestrator (< 50 source lines) that picks between
the live and fresh paths. Each phase is also < 50 lines, enforced
by ``tests/test_wechat_ilink_split.py`` (R1-4b size contract).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

logger = logging.getLogger(__name__)


# Image extensions that go through ``send_image_file``; everything else
# goes through ``send_document``. Mirrors the dispatch table in the
# original ``send_wechat_direct`` function (R1-4b extraction).
_IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}


def _phase_direct_resolve_credentials(
    extra: Dict[str, Any],
    token: Optional[str],
) -> Dict[str, Any]:
    """Phase D1: read ``extra`` + ``WECHAT_*`` env vars.

    Returns a dict with one of two shapes:

    * Success: ``{"account_id": ..., "token": ..., "base_url": ...,
      "cdn_base_url": ...}`` — caller proceeds.
    * Failure: ``{"error": "..."}`` — caller returns immediately
      (matches the original ``send_wechat_direct`` return contract).
    """
    from butler.gateway.platforms.wechat_ilink import (
        ILINK_BASE_URL,
        WECHAT_CDN_BASE_URL,
    )

    account_id = str(
        extra.get("account_id") or os.getenv("WECHAT_ACCOUNT_ID", "")
    ).strip()
    base_url = str(
        extra.get("base_url") or os.getenv("WECHAT_BASE_URL", ILINK_BASE_URL)
    ).strip().rstrip("/")
    cdn_base_url = str(
        extra.get("cdn_base_url")
        or os.getenv("WECHAT_CDN_BASE_URL", WECHAT_CDN_BASE_URL)
    ).strip().rstrip("/")
    resolved_token = str(
        token or extra.get("token") or os.getenv("WECHAT_TOKEN", "")
    ).strip()
    if not resolved_token:
        return {
            "error": "WeChat token missing. Configure WECHAT_TOKEN or platforms.wechat.token."
        }
    if not account_id:
        return {
            "error": "WeChat account ID missing. Configure WECHAT_ACCOUNT_ID or platforms.wechat.extra.account_id."
        }
    return {
        "account_id": account_id,
        "token": resolved_token,
        "base_url": base_url,
        "cdn_base_url": cdn_base_url,
    }


def _build_success_dict(
    *,
    chat_id: str,
    last_result: Optional[Any],
    context_token: Optional[str],
) -> Dict[str, Any]:
    """Shared success-envelope builder for the two delivery paths."""
    return {
        "success": True,
        "platform": "wechat",
        "chat_id": chat_id,
        "message_id": last_result.message_id if last_result else None,
        "context_token_used": bool(context_token),
    }


async def _phase_direct_send_via_live_adapter(
    live_adapter: "WeChatAdapter",
    *,
    chat_id: str,
    message: str,
    media_files: Optional[List[Tuple[str, bool]]],
    context_token: Optional[str],
) -> Dict[str, Any]:
    """Phase D2: deliver via the live adapter for the same token.

    Reuses the adapter's existing ``send_session`` and its
    already-warm ``WeChatAdapter`` state. Returns either a success
    dict (matching the host's return contract) or an error dict.
    """
    return await _dispatch_message_and_media(
        live_adapter,
        chat_id=chat_id,
        message=message,
        media_files=media_files,
        context_token=context_token,
    )


async def _phase_direct_send_via_fresh_adapter(
    *,
    creds: Dict[str, str],
    chat_id: str,
    message: str,
    media_files: Optional[List[Tuple[str, bool]]],
    context_token: Optional[str],
    token_store: Any,
) -> Dict[str, Any]:
    """Phase D3: build a one-shot ``WeChatAdapter`` and deliver.

    The fresh adapter is wired with a new ``aiohttp`` session and
    the same ``token_store`` so the inbound ``context_token`` is
    honored. Returns a success dict or an error dict (same contract
    as the live-adapter path).
    """
    import aiohttp

    from butler.gateway.platforms.wechat_ilink import _make_ssl_connector

    async with aiohttp.ClientSession(
        trust_env=True, connector=_make_ssl_connector(),
    ) as session:
        adapter = _build_fresh_adapter(creds, session=session, token_store=token_store)
        return await _dispatch_message_and_media(
            adapter,
            chat_id=chat_id,
            message=message,
            media_files=media_files,
            context_token=context_token,
        )


def _build_fresh_adapter(
    creds: Dict[str, str],
    *,
    session: Any,
    token_store: Any,
) -> "WeChatAdapter":
    """Internal helper: instantiate + wire a one-shot ``WeChatAdapter``.

    Extracted from :func:`_phase_direct_send_via_fresh_adapter` to
    keep that phase under the 50-line cap. Patches the
    transport-agnostic state (``_send_session`` / ``_token`` /
    ``_account_id`` / ...) so the adapter can dispatch without
    going through ``connect()``.
    """
    from butler.gateway.platforms.types import PlatformConfig

    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

    account_id = creds["account_id"]
    resolved_token = creds["token"]
    base_url = creds["base_url"]
    cdn_base_url = creds["cdn_base_url"]

    adapter = WeChatAdapter(
        PlatformConfig(
            token=resolved_token,
            extra={
                "account_id": account_id,
                "base_url": base_url,
                "cdn_base_url": cdn_base_url,
            },
        )
    )
    adapter._send_session = session
    adapter._session = session
    adapter._token = resolved_token
    adapter._account_id = account_id
    adapter._base_url = base_url
    adapter._cdn_base_url = cdn_base_url
    adapter._token_store = token_store
    return adapter


async def _dispatch_message_and_media(
    adapter: "WeChatAdapter",
    *,
    chat_id: str,
    message: str,
    media_files: Optional[List[Tuple[str, bool]]],
    context_token: Optional[str],
) -> Dict[str, Any]:
    """Internal helper: shared text+media dispatch loop.

    Used by both :func:`_phase_direct_send_via_live_adapter` and
    :func:`_phase_direct_send_via_fresh_adapter`. Returns a success
    dict or an error dict (mirrors the original ``send_wechat_direct``
    return contract).
    """
    last_result: Optional[Any] = None
    cleaned = adapter.format_message(message)
    if cleaned:
        last_result = await adapter.send(chat_id, cleaned)
        if not last_result.success:
            return {"error": f"WeChat send failed: {last_result.error}"}
    for media_path, _is_voice in media_files or []:
        ext = Path(media_path).suffix.lower()
        if ext in _IMAGE_EXTS:
            last_result = await adapter.send_image_file(chat_id, media_path)
        else:
            last_result = await adapter.send_document(chat_id, media_path)
        if not last_result.success:
            return {"error": f"WeChat media send failed: {last_result.error}"}
    return _build_success_dict(
        chat_id=chat_id,
        last_result=last_result,
        context_token=context_token,
    )


__all__ = [
    "_phase_direct_resolve_credentials",
    "_phase_direct_send_via_live_adapter",
    "_phase_direct_send_via_fresh_adapter",
]
