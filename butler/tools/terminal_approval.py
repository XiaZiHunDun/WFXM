"""Terminal exec approval binding (OpenClaw exec-approvals subset)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path

_TTL_SEC = 300.0


def _approvals_dir() -> Path:
    from butler.config import get_butler_home

    path = Path(get_butler_home()) / "exec_approvals"
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
    from butler.tools.terminal_approval_ops import canonicalize_command_safe

    canonical = canonicalize_command_safe(command)
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
    unsandboxed: bool = False,
) -> str:
    fp = argv_fingerprint(command, cwd=cwd)
    record = {
        "command": command.strip(),
        "cwd": (cwd or "").strip(),
        "session_key": str(session_key or "").strip(),
        "unsandboxed": bool(unsandboxed),
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

    from butler.tools.terminal_approval_ops import try_auto_review_terminal_safe

    review = try_auto_review_terminal_safe(command)
    if review is not None and review.allowed and not review.skipped:
        store_approval(command, cwd=cwd, session_key=session_key, ttl_sec=300.0)
        return None
    fp = argv_fingerprint(command, cwd=cwd)
    path = _approvals_dir() / f"{fp}.json"
    from butler.core.approval_cards import format_terminal_exec_card

    if not path.is_file():
        return str(format_terminal_exec_card(
            command,
            reason="终端命令需 Owner 批准后再执行",
        ))
    from butler.tools.terminal_approval_ops import read_approval_record_safe

    data = read_approval_record_safe(path)
    if data is None:
        return str(format_terminal_exec_card(command, reason="批准记录损坏，请重新批准"))
    if time.time() > float(data.get("expires_at") or 0):
        path.unlink(missing_ok=True)
        return str(format_terminal_exec_card(command, reason="批准已过期（5 分钟），请重新批准"))
    if data.get("command", "").strip() != command.strip():
        return str(format_terminal_exec_card(
            command,
            reason="命令与批准记录不一致，请重新 /批准执行",
        ))
    recorded_sk = str(data.get("session_key") or "").strip()
    want_sk = str(session_key or "").strip()
    if recorded_sk and want_sk and recorded_sk != want_sk:
        return str(format_terminal_exec_card(
            command,
            reason="批准属于其他会话，请在本会话重新 /批准执行",
        ))
    return None


def approval_allows_unsandboxed(
    command: str,
    *,
    cwd: str = "",
    session_key: str = "",
) -> bool:
    """True when a valid approval record explicitly allows running outside sandbox."""
    fp = argv_fingerprint(command, cwd=cwd)
    path = _approvals_dir() / f"{fp}.json"
    if not path.is_file():
        return False
    from butler.tools.terminal_approval_ops import read_approval_record_safe

    data = read_approval_record_safe(path)
    if data is None:
        return False
    if time.time() > float(data.get("expires_at") or 0):
        path.unlink(missing_ok=True)
        return False
    if data.get("command", "").strip() != command.strip():
        return False
    recorded_sk = str(data.get("session_key") or "").strip()
    want_sk = str(session_key or "").strip()
    if recorded_sk and want_sk and recorded_sk != want_sk:
        return False
    return bool(data.get("unsandboxed"))


def parse_approve_command(text: str) -> str | None:
    """Extract command from `/批准执行 ...` or `/approve-exec ...`."""
    raw = (text or "").strip()
    for prefix in ("/批准执行", "/approve-exec", "/approve_exec"):
        if raw.lower().startswith(prefix.lower()):
            rest = raw[len(prefix) :].strip()
            return rest or None
    return None


def parse_approve_unsandboxed_command(text: str) -> str | None:
    """Extract command from ``/批准沙箱外`` or ``/approve-unsandboxed``."""
    raw = (text or "").strip()
    for prefix in ("/批准沙箱外", "/approve-unsandboxed", "/approve_unsandboxed"):
        if raw.lower().startswith(prefix.lower()):
            rest = raw[len(prefix) :].strip()
            return rest or None
    return None
