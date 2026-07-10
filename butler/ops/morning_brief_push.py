"""Opt-in morning /简报 push to Owner WeChat (WS-E backlog)."""

from __future__ import annotations

from typing import cast

import logging
import os

logger = logging.getLogger(__name__)


def morning_brief_enabled() -> bool:
    return os.getenv("BUTLER_MORNING_BRIEF", "0").strip().lower() in (
        "1",
        "true",
        "yes",
    )


def resolve_morning_brief_session_key() -> str:
    from butler.gateway.owner_gate import resolve_owner_wechat_chat_id
    from butler.session.keys import build_session_key

    cid = resolve_owner_wechat_chat_id()
    if not cid:
        return ""
    project = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip()
    return cast(str, build_session_key(platform="wechat", chat_id=cid, project=project))


def build_morning_brief_text(*, session_key: str = "") -> str:
    from butler.orchestrator import ButlerOrchestrator

    sk = str(session_key or "").strip() or resolve_morning_brief_session_key()
    if not sk:
        return ""
    orch = ButlerOrchestrator(user_id="owner", channel="cron")
    from butler.ops.butler_inbox import format_owner_brief

    return cast(str, format_owner_brief(orch, sk, health={}))


def push_morning_brief(*, session_key: str = "") -> dict[str, object]:
    """Push /简报-style text to Owner WeChat when opt-in."""
    if not morning_brief_enabled():
        return {"ok": False, "reason": "disabled", "env": "BUTLER_MORNING_BRIEF"}
    body = build_morning_brief_text(session_key=session_key)
    if not body.strip():
        return {"ok": False, "reason": "empty_brief"}
    from butler.runtime.notify import push_runtime_message

    sent = push_runtime_message("📬 晨间简报", body)
    return {"ok": bool(sent), "chars": len(body)}


__all__ = [
    "build_morning_brief_text",
    "morning_brief_enabled",
    "push_morning_brief",
    "resolve_morning_brief_session_key",
]
