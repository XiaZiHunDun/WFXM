"""Push runtime summaries to Owner WeChat."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from butler.config import get_butler_home

logger = logging.getLogger(__name__)

_LAST_PUSH_FILE = "runtime/last_push_at.json"


def resolve_owner_wechat_chat_id() -> str:
    from butler.gateway.owner_gate import resolve_owner_wechat_chat_id as _resolve

    return _resolve()


def runtime_push_enabled() -> bool:
    v = os.getenv("BUTLER_RUNTIME_PUSH", "1").strip().lower()
    return v in ("1", "true", "yes", "on")


def _push_cooldown_seconds() -> float:
    raw = os.getenv("BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS", "25").strip()
    try:
        return max(0.0, float(raw))
    except ValueError:
        return 25.0


def _last_push_path() -> Path:
    return get_butler_home() / _LAST_PUSH_FILE


def _read_last_push_monotonic() -> float | None:
    path = _last_push_path()
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return float(data.get("monotonic"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return None


def _write_last_push_monotonic(ts: float) -> None:
    path = _last_push_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"monotonic": ts, "wall": time.time()}, indent=0),
        encoding="utf-8",
    )


def wait_wechat_push_cooldown() -> float:
    """Shared cooldown for runtime push and gateway completion push."""
    return _wait_push_cooldown()


def mark_wechat_push_sent() -> None:
    """Record a successful WeChat push (starts cooldown window)."""
    _write_last_push_monotonic(time.monotonic())


def _wait_push_cooldown() -> float:
    """Sleep if the previous runtime push was too recent. Returns seconds slept."""
    cooldown = _push_cooldown_seconds()
    if cooldown <= 0:
        return 0.0
    last = _read_last_push_monotonic()
    if last is None:
        return 0.0
    elapsed = time.monotonic() - last
    if elapsed >= cooldown:
        return 0.0
    wait = cooldown - elapsed
    logger.info(
        "Runtime push cooldown: sleeping %.1fs (BUTLER_RUNTIME_PUSH_COOLDOWN_SECONDS=%.0f)",
        wait,
        cooldown,
    )
    time.sleep(wait)
    return wait


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

    wait_wechat_push_cooldown()
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
        ok = not result.get("error")
        if ok:
            mark_wechat_push_sent()
        else:
            err = result.get("error")
            logger.warning("Runtime wechat push failed: %s", err)
            if should_enqueue_wechat_push_failure(err):
                from butler.runtime.push_queue import enqueue_failed_push

                enqueue_failed_push(title, body, chat_id=cid)
        return ok
    except Exception as exc:
        logger.exception("Runtime wechat push failed: %s", exc)
        if should_enqueue_wechat_push_failure(str(exc)):
            from butler.runtime.push_queue import enqueue_failed_push

            enqueue_failed_push(title, body, chat_id=cid)
        return False


def should_enqueue_wechat_push_failure(err: str | None) -> bool:
    """Whether a failed WeChat push should be queued for retry."""
    if _should_enqueue_on_failure(err):
        return True
    msg = (err or "").lower()
    return any(
        token in msg
        for token in (
            "timeout",
            "timed out",
            "connection",
            "network",
            "refused",
            "unavailable",
            "503",
            "502",
        )
    )


def _should_enqueue_on_failure(err: str | None) -> bool:
    if os.getenv("BUTLER_RUNTIME_PUSH_QUEUE", "1").strip().lower() in (
        "0",
        "false",
        "no",
        "off",
    ):
        return False
    msg = (err or "").lower()
    return "rate limit" in msg or "rate limited" in msg
