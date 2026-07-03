"""WeChat QR-login sub-phases (ENG-5 — extracted from phases.py)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Optional, Tuple

if TYPE_CHECKING:
    import aiohttp

logger = logging.getLogger(__name__)


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
    from butler.gateway.platforms.wechat_ilink.qr_phases_ops import fetch_qr_response_safe

    qr_resp = await fetch_qr_response_safe(
        lambda: _api_get(
            session,
            base_url=base_url,
            endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
            timeout_ms=QR_TIMEOUT_MS,
        ),
        label="failed to fetch QR code",
    )
    if qr_resp is None:
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
    from butler.gateway.platforms.wechat_ilink.qr_phases_ops import render_qr_ascii_safe

    render_qr_ascii_safe(qr_scan_data)


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
    from butler.gateway.platforms.wechat_ilink.qr_phases_ops import poll_qr_api_safe

    status_resp = await poll_qr_api_safe(
        lambda: _api_get(
            session,
            base_url=current_base_url,
            endpoint=f"{EP_GET_QR_STATUS}?qrcode={qrcode_value}",
            timeout_ms=QR_TIMEOUT_MS,
        ),
    )
    if status_resp is None:
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
    from butler.gateway.platforms.wechat_ilink.qr_phases_ops import fetch_qr_response_safe

    qr_resp = await fetch_qr_response_safe(
        lambda: _api_get(
            session,
            base_url=base_url,
            endpoint=f"{EP_GET_BOT_QR}?bot_type={bot_type}",
            timeout_ms=QR_TIMEOUT_MS,
        ),
        label="QR refresh failed",
    )
    if qr_resp is None:
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
    "QrLoginState",
    "_phase_qr_finalize",
    "_phase_qr_poll_iteration",
    "_phase_qr_poll_step",
    "_phase_qr_refresh",
    "_phase_qr_render",
    "_phase_qr_request_code",
    "_qr_handle_expired",
]
