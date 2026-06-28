"""WeChat connect sub-phases (ENG-5 — extracted from phases.py)."""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

logger = logging.getLogger(__name__)


def _phase_connect_validate(adapter: "WeChatAdapter") -> bool:
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
    if not _acquire_token_lock(adapter):
        return
    _open_aiohttp_sessions(adapter)
    _start_poll_and_register(adapter)


def _acquire_token_lock(adapter: "WeChatAdapter") -> bool:
    try:
        return bool(adapter._acquire_platform_lock(
            "wechat-bot-token", adapter._token, "WeChat bot token",
        ))
    except Exception as exc:
        logger.debug(
            "[%s] Token lock unavailable (non-fatal): %s", adapter.name, exc,
        )
        return True


def _open_aiohttp_sessions(adapter: "WeChatAdapter") -> None:
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
    from butler.gateway.platforms.wechat_ilink import _safe_id
    from butler.gateway.platforms.wechat_ilink.registry import _ADAPTER_REGISTRY

    adapter._token_store.restore(adapter._account_id)
    adapter._poll_task = asyncio.create_task(adapter._poll_loop(), name="wechat-poll")
    adapter._mark_connected()
    _ADAPTER_REGISTRY.register(adapter._token, adapter)
    logger.info(
        "[%s] Connected account=%s base=%s",
        adapter.name, _safe_id(adapter._account_id), adapter._base_url,
    )
    if adapter._group_policy != "disabled":
        _warn_group_policy_limitation(adapter)


def _warn_group_policy_limitation(adapter: "WeChatAdapter") -> None:
    logger.warning(
        "[%s] WECHAT_GROUP_POLICY=%s is set, but QR-login connects an iLink bot "
        "identity (e.g. ...@im.bot) which typically cannot be invited into ordinary "
        "WeChat groups. iLink usually does not deliver ordinary-group events for "
        "these accounts, so group messages may never reach Hermes regardless of this "
        "policy. If group delivery doesn't work, the limitation is on the iLink side, "
        "not in Hermes.",
        adapter.name, adapter._group_policy,
    )


__all__ = [
    "_acquire_token_lock",
    "_open_aiohttp_sessions",
    "_phase_connect_open_sessions",
    "_phase_connect_validate",
    "_start_poll_and_register",
    "_warn_group_policy_limitation",
]
