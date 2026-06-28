"""WeChat poll-loop sub-phases (ENG-5 — extracted from phases.py)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, Dict, List, Tuple

if TYPE_CHECKING:
    from butler.gateway.platforms.wechat_ilink import WeChatAdapter

logger = logging.getLogger(__name__)


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


__all__ = ["_phase_poll_handle_response"]
