"""Push runtime summaries to Owner WeChat."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def resolve_owner_wechat_chat_id() -> str:
    """BUTLER_OWNER_WECHAT_ID, else first WECHAT_ALLOWED_USERS entry."""
    cid = os.getenv("BUTLER_OWNER_WECHAT_ID", "").strip()
    if cid:
        return cid
    allow = os.getenv("WECHAT_ALLOWED_USERS", "").strip()
    if allow:
        return allow.split(",")[0].strip()
    return ""


def runtime_push_enabled() -> bool:
    v = os.getenv("BUTLER_RUNTIME_PUSH", "1").strip().lower()
    return v in ("1", "true", "yes", "on")


def _wechat_extra() -> dict[str, Any]:
    return {
        "account_id": os.getenv("WECHAT_ACCOUNT_ID", "").strip(),
        "token": os.getenv("WECHAT_TOKEN", "").strip(),
        "base_url": os.getenv("WECHAT_BASE_URL", "").strip(),
    }


def push_runtime_message(title: str, body: str, *, chat_id: str | None = None) -> bool:
    """Send summary to Owner WeChat. Returns True if send attempted and succeeded."""
    if not runtime_push_enabled():
        logger.info("Runtime push disabled (BUTLER_RUNTIME_PUSH)")
        return False
    cid = (chat_id or "").strip() or resolve_owner_wechat_chat_id()
    if not cid:
        logger.warning("No BUTLER_OWNER_WECHAT_ID / WECHAT_ALLOWED_USERS for runtime push")
        return False
    extra = _wechat_extra()
    if not extra.get("token"):
        logger.warning("WECHAT_TOKEN missing — cannot push runtime result")
        return False

    text = f"{title}\n\n{body}".strip()
    if len(text) > 4000:
        text = text[:3997] + "..."

    try:
        from butler.gateway.platforms.wechat_ilink import send_wechat_direct

        result = asyncio.run(
            send_wechat_direct(
                extra=extra,
                token=str(extra.get("token") or ""),
                chat_id=cid,
                message=text,
            )
        )
        return not result.get("error")
    except Exception as exc:
        logger.exception("Runtime wechat push failed: %s", exc)
        return False
