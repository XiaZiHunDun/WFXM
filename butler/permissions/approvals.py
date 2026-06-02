"""Session-scoped permission approvals (OpenCode once / always subset)."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.config import get_butler_home

logger = logging.getLogger(__name__)

_ONCE_TTL_SEC = 300.0


@dataclass(frozen=True)
class ApprovalRequest:
    permission: str
    tool: str
    pattern: str
    reason: str = ""

    def fingerprint(self) -> str:
        payload = json.dumps(
            {
                "permission": self.permission,
                "tool": self.tool,
                "pattern": self.pattern,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def once_ttl_seconds() -> float:
    try:
        return max(60.0, float(os.getenv("BUTLER_PERMISSION_ONCE_TTL", "") or _ONCE_TTL_SEC))
    except ValueError:
        return _ONCE_TTL_SEC


def _safe_segment(value: str) -> str:
    import hashlib

    raw = str(value or "").strip() or "_global"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def approvals_path(session_key: str) -> Path:
    sk = _safe_segment(session_key)
    path = get_butler_home() / "sessions" / sk / "approvals.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load(session_key: str) -> dict[str, Any]:
    path = approvals_path(session_key)
    if not path.is_file():
        return {"always": [], "once": [], "pending": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"always": [], "once": [], "pending": None}
    if not isinstance(data, dict):
        return {"always": [], "once": [], "pending": None}
    data.setdefault("always", [])
    data.setdefault("once", [])
    return data


def _save(session_key: str, data: dict[str, Any]) -> None:
    path = approvals_path(session_key)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _purge_once(entries: list[Any]) -> list[dict[str, Any]]:
    now = time.time()
    out: list[dict[str, Any]] = []
    for row in entries:
        if not isinstance(row, dict):
            continue
        exp = float(row.get("expires_at") or 0)
        if exp > now:
            out.append(row)
    return out


def save_pending(session_key: str, request: ApprovalRequest) -> str:
    """Store last ask for Owner /批准一次."""
    if not str(session_key or "").strip():
        return ""
    data = _load(session_key)
    fp = request.fingerprint()
    data["pending"] = {
        "permission": request.permission,
        "tool": request.tool,
        "pattern": request.pattern,
        "reason": request.reason,
        "fingerprint": fp,
        "requested_at": time.time(),
    }
    _save(session_key, data)
    return fp


def grant_once(session_key: str, *, fingerprint: str = "") -> str | None:
    """Approve pending or explicit fingerprint for one TTL window."""
    sk = str(session_key or "").strip()
    if not sk:
        return "无有效会话"
    data = _load(sk)
    pending = data.get("pending")
    fp = str(fingerprint or "").strip()
    if not fp and isinstance(pending, dict):
        fp = str(pending.get("fingerprint") or "")
    if not fp:
        return "暂无待批准项；请先触发需确认的工具调用"
    row = pending if isinstance(pending, dict) and pending.get("fingerprint") == fp else None
    if row is None:
        if isinstance(pending, dict):
            logger.warning(
                "approvals.grant_once fingerprint mismatch: pending.fp=%s got.fp=%s session=%s",
                pending.get("fingerprint"),
                fp,
                sk,
            )
        return "指纹不匹配；请重新发起待批准项"
    data["once"] = _purge_once(data.get("once") or [])
    data["once"].append(
        {
            "permission": row.get("permission"),
            "tool": row.get("tool"),
            "pattern": row.get("pattern"),
            "fingerprint": fp,
            "expires_at": time.time() + once_ttl_seconds(),
        }
    )
    data["pending"] = None
    _save(sk, data)
    perm = str(row.get("permission") or "?")
    return f"已批准一次：{perm}（{int(once_ttl_seconds())} 秒内有效）"


def grant_always(
    session_key: str,
    *,
    permission: str,
    tool: str = "*",
    pattern: str = "*",
) -> str:
    sk = str(session_key or "").strip()
    if not sk:
        return "无有效会话"
    perm = str(permission or "").strip()
    if not perm:
        return "请指定权限名，例如：/始终允许 external_directory 或 /始终允许 write_file:.env*"
    data = _load(sk)
    always = [r for r in (data.get("always") or []) if isinstance(r, dict)]
    entry = {
        "permission": perm,
        "tool": str(tool or "*").strip() or "*",
        "pattern": str(pattern or "*").strip() or "*",
        "created_at": time.time(),
    }
    always = [r for r in always if not (
        r.get("permission") == entry["permission"]
        and r.get("tool") == entry["tool"]
        and r.get("pattern") == entry["pattern"]
    )]
    always.append(entry)
    data["always"] = always
    data["pending"] = None
    _save(sk, data)
    return f"已始终允许：{perm} · 工具 {entry['tool']} · 模式 {entry['pattern']}"


def list_always(session_key: str) -> list[dict[str, Any]]:
    data = _load(session_key)
    return [r for r in (data.get("always") or []) if isinstance(r, dict)]


def clear_pending(session_key: str) -> None:
    data = _load(session_key)
    data["pending"] = None
    _save(session_key, data)


def _match_entry(
    entry: dict[str, Any],
    request: ApprovalRequest,
) -> bool:
    perm = str(entry.get("permission") or "")
    if perm and perm != request.permission:
        return False
    tool_pat = str(entry.get("tool") or "*")
    if tool_pat != "*" and tool_pat != request.tool:
        return False
    from butler.permissions.rules import match_path_glob

    pat = str(entry.get("pattern") or "*")
    if pat == "*":
        return True
    return match_path_glob(pat, request.pattern)


def is_approved(session_key: str, request: ApprovalRequest) -> bool:
    sk = str(session_key or "").strip()
    if not sk:
        return False
    data = _load(sk)
    for row in data.get("always") or []:
        if isinstance(row, dict) and _match_entry(row, request):
            return True
    fp = request.fingerprint()
    now = time.time()
    for row in _purge_once(data.get("once") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("fingerprint") or "") == fp:
            return True
        if _match_entry(row, request) and float(row.get("expires_at") or 0) > now:
            return True
    return False
