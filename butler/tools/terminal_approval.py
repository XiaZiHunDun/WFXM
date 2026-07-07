"""Terminal exec approval binding (OpenClaw exec-approvals subset)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from pathlib import Path

from butler.config import get_butler_home
from butler.contracts.approval_registry import get_approval_store
from butler.contracts.approval_store_impl import grant_terminal_exec_once
from butler.core.approval_cards import format_terminal_exec_card
from butler.permissions.approvals import _load, _purge_once
from butler.tools.terminal_approval_ops import canonicalize_command_safe
from butler.tools.terminal_approval_ops import try_auto_review_terminal_safe

logger = logging.getLogger(__name__)

_TTL_SEC = 300.0
_GLOBAL_TERMINAL_SESSION_KEY = "__terminal_global__"


def _resolve_session_key(session_key: str) -> str:
    sk = str(session_key or "").strip()
    return sk or _GLOBAL_TERMINAL_SESSION_KEY


def _legacy_approval_path(fp: str) -> Path:
    return Path(get_butler_home()) / "exec_approvals" / f"{fp}.json"


def approval_required() -> bool:
    return os.getenv("BUTLER_TERMINAL_REQUIRE_APPROVAL", "0").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def argv_fingerprint(command: str, *, cwd: str = "") -> str:
    canonical = canonicalize_command_safe(command)
    payload = json.dumps(
        {"command": canonical, "cwd": (cwd or "").strip()},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _migrate_legacy_exec_approval(
    command: str,
    *,
    cwd: str,
    session_key: str,
    fp: str,
) -> bool:
    """Import one-shot legacy ``exec_approvals/{fp}.json`` into approvals.json."""
    from butler.tools.terminal_approval_ops import read_approval_record_safe

    path = _legacy_approval_path(fp)
    if not path.is_file():
        return False
    data = read_approval_record_safe(path)
    try:
        if data is None:
            path.unlink(missing_ok=True)
            return False
        expires = float(data.get("expires_at") or 0)
        if time.time() > expires:
            path.unlink(missing_ok=True)
            return False
        if str(data.get("command") or "").strip() != command.strip():
            return False
        sk = _resolve_session_key(str(data.get("session_key") or session_key))
        grant_terminal_exec_once(
            sk,
            fingerprint=fp,
            command=command,
            ttl_sec=max(1.0, expires - time.time()),
            unsandboxed=bool(data.get("unsandboxed")),
        )
        path.unlink(missing_ok=True)
        return True
    except OSError as exc:
        logger.debug("legacy exec_approval migrate failed: %s", exc)
        return False


def store_approval(
    command: str,
    *,
    cwd: str = "",
    session_key: str = "",
    ttl_sec: float | None = None,
    unsandboxed: bool = False,
) -> str:
    fp = argv_fingerprint(command, cwd=cwd)
    sk = _resolve_session_key(session_key)
    grant_terminal_exec_once(
        sk,
        fingerprint=fp,
        command=command,
        ttl_sec=ttl_sec,
        unsandboxed=unsandboxed,
    )
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

    review = try_auto_review_terminal_safe(command)
    if review is not None and review.allowed and not review.skipped:
        store_approval(command, cwd=cwd, session_key=session_key, ttl_sec=300.0)
        return None

    fp = argv_fingerprint(command, cwd=cwd)
    sk = _resolve_session_key(session_key)
    _migrate_legacy_exec_approval(command, cwd=cwd, session_key=sk, fp=fp)

    store = get_approval_store()
    if store is not None and store.is_approved(
        sk,
        permission="terminal_exec",
        tool="terminal",
        pattern=fp,
    ):
        return None

    return str(
        format_terminal_exec_card(
            command,
            reason="终端命令需 Owner 批准后再执行",
        )
    )


def approval_allows_unsandboxed(
    command: str,
    *,
    cwd: str = "",
    session_key: str = "",
) -> bool:
    """True when a valid approval record explicitly allows running outside sandbox."""
    fp = argv_fingerprint(command, cwd=cwd)
    sk = _resolve_session_key(session_key)
    _migrate_legacy_exec_approval(command, cwd=cwd, session_key=sk, fp=fp)
    data = _load(sk)
    now = time.time()
    for row in _purge_once(data.get("once") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("permission") or "") != "terminal_exec":
            continue
        if str(row.get("pattern") or "") != fp and str(row.get("fingerprint") or "") != fp:
            continue
        if not bool(row.get("unsandboxed")):
            continue
        if str(row.get("command") or "").strip() != command.strip():
            continue
        if float(row.get("expires_at") or 0) <= now:
            continue
        return True
    return False


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
