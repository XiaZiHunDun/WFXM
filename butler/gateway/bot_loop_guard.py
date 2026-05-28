"""Suppress bot-to-bot reply loops in group chats (OpenClaw pair-loop-guard subset)."""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from collections import deque

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_WINDOW_SEC = 120.0
_LOCK = threading.RLock()
_PAIR_COUNTS: dict[str, deque[float]] = {}


def bot_loop_guard_enabled() -> bool:
    return env_truthy("BUTLER_BOT_LOOP_GUARD", default=False)


def pair_threshold() -> int:
    try:
        return max(2, int(os.getenv("BUTLER_BOT_LOOP_PAIR_THRESHOLD", "6")))
    except ValueError:
        return 6


def _pair_key(chat_id: str, sender_id: str) -> str:
    return f"{chat_id}::{sender_id}"


def _is_whitelisted(chat_id: str) -> bool:
    raw = os.getenv("BUTLER_BOT_LOOP_WHITELIST", "").strip()
    if not raw:
        return False
    allowed = {x.strip() for x in raw.split(",") if x.strip()}
    return chat_id in allowed


def looks_like_bot_sender(sender_id: str, text: str) -> bool:
    """Heuristic: bot accounts or messages that @ other bots."""
    sid = str(sender_id or "").lower()
    if "bot" in sid or sid.endswith("@openim"):
        return True
    if re.search(r"@\S*bot\S*", text or "", re.I):
        return True
    return False


def record_and_should_suppress(
    *,
    chat_id: str,
    sender_id: str,
    text: str = "",
) -> tuple[bool, str]:
    """Return (suppress, reason)."""
    if not bot_loop_guard_enabled():
        return False, ""
    cid = str(chat_id or "").strip() or "unknown"
    if _is_whitelisted(cid):
        return False, ""
    if not looks_like_bot_sender(sender_id, text):
        return False, ""

    key = _pair_key(cid, sender_id)
    now = time.monotonic()
    with _LOCK:
        bucket = _PAIR_COUNTS.setdefault(key, deque())
        while bucket and (now - bucket[0]) > _WINDOW_SEC:
            bucket.popleft()
        bucket.append(now)
        count = len(bucket)

    if count >= pair_threshold():
        logger.info(
            "Bot loop guard suppress chat=%s sender=%s count=%d",
            cid,
            sender_id,
            count,
        )
        try:
            from butler.core.session_transcript import record_generic_event

            record_generic_event(
                f"wx:{cid}",
                "bot_loop_suppressed",
                {"sender": sender_id, "count": count},
            )
        except Exception as exc:
            logger.debug("record and should suppress skipped: %s", exc)
        return True, f"bot_loop_guard count={count}"
    return False, ""
