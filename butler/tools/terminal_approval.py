"""Terminal exec approval binding (OpenClaw exec-approvals subset)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_TTL_SEC = 300.0


def _approvals_dir() -> Path:
    from butler.config import get_butler_home

    path = get_butler_home() / "exec_approvals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def approval_required() -> bool:
    return os.getenv("BUTLER_TERMINAL_REQUIRE_APPROVAL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def argv_fingerprint(command: str, *, cwd: str = "") -> str:
    try:
        from butler.tools.command_canonicalize import canonicalize_command_for_approval

        canonical = canonicalize_command_for_approval(command)
    except Exception:
        canonical = (command or "").strip()
    payload = json.dumps(
        {"command": canonical, "cwd": (cwd or "").strip()},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def store_approval(
    command: str,
    *,
    cwd: str = "",
    session_key: str = "",
    ttl_sec: float | None = None,
) -> str:
    fp = argv_fingerprint(command, cwd=cwd)
    record = {
        "command": command.strip(),
        "cwd": (cwd or "").strip(),
        "session_key": str(session_key or "").strip(),
        "expires_at": time.time() + (ttl_sec if ttl_sec is not None else _TTL_SEC),
    }
    path = _approvals_dir() / f"{fp}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return fp


def check_approval(
    command: str,
    *,
    cwd: str = "",
    session_key: str = "",
) -> str | None:
    """Return error message if not approved; None if ok or approval not required."""
    if not approval_required():
        return None

    try:
        from butler.core.auto_review import try_auto_review_terminal

        review = try_auto_review_terminal(command, diagnostics=None)
        if review.allowed and not review.skipped:
            store_approval(command, cwd=cwd, session_key=session_key, ttl_sec=300.0)
            return None
    except Exception as exc:
        logger.debug("check approval skipped: %s", exc)
    fp = argv_fingerprint(command, cwd=cwd)
    path = _approvals_dir() / f"{fp}.json"
    if not path.is_file():
        return (
            "terminal 需 Owner 批准：发「/批准执行 <完整命令>」后再重试 "
            f"(fp={fp[:8]})"
        )
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return "terminal 批准记录损坏"
    if not isinstance(data, dict):
        return "terminal 批准记录无效"
    if time.time() > float(data.get("expires_at") or 0):
        path.unlink(missing_ok=True)
        return "terminal 批准已过期，请重新 /批准执行"
    if data.get("command", "").strip() != command.strip():
        return "terminal 命令与批准记录不一致"
    recorded_sk = str(data.get("session_key") or "").strip()
    want_sk = str(session_key or "").strip()
    if recorded_sk and want_sk and recorded_sk != want_sk:
        return "terminal 批准记录属于其他会话，请在本会话重新 /批准执行"
    return None


def parse_approve_command(text: str) -> str | None:
    """Extract command from `/批准执行 ...` or `/approve-exec ...`."""
    raw = (text or "").strip()
    for prefix in ("/批准执行", "/approve-exec", "/approve_exec"):
        if raw.lower().startswith(prefix.lower()):
            rest = raw[len(prefix) :].strip()
            return rest or None
    return None
