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


def is_approved(
    session_key: str,
    request: ApprovalRequest,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> bool:
    """Sprint 24 P1-3.2: 加 diagnostics kw-only 形参, 命中时写入 source.

    Note: diagnostics 是向后兼容 kw-only 形参, 现有 3 个调用点 (doom_loop /
    rules / mcp) 不传也工作正常; 传则可在 /诊断中看到本次调用命中信息.
    """
    sk = str(session_key or "").strip()
    if not sk:
        return False
    data = _load(sk)
    for row in data.get("always") or []:
        if isinstance(row, dict) and _match_entry(row, request):
            if diagnostics is not None:
                diagnostics["approval_cache_hit"] = True
                diagnostics["approval_cache_source"] = "always"
            return True
    fp = request.fingerprint()
    now = time.time()
    for row in _purge_once(data.get("once") or []):
        if not isinstance(row, dict):
            continue
        if str(row.get("fingerprint") or "") == fp:
            if diagnostics is not None:
                diagnostics["approval_cache_hit"] = True
                diagnostics["approval_cache_source"] = "once"
            return True
        if _match_entry(row, request) and float(row.get("expires_at") or 0) > now:
            if diagnostics is not None:
                diagnostics["approval_cache_hit"] = True
                diagnostics["approval_cache_source"] = "once"
            return True
    return False


def revoke_always(
    session_key: str,
    *,
    permission: str = "",
    tool: str = "",
    pattern: str = "",
) -> str:
    """Sprint 24 P1-3.2: 按 permission/tool/pattern 过滤撤销 always 记录.

    全空过滤时返错误, 防止误删. 任意一个非空过滤都参与匹配.
    """
    sk = str(session_key or "").strip()
    if not sk:
        return "无有效会话"
    perm_f = str(permission or "").strip()
    tool_f = str(tool or "").strip()
    pat_f = str(pattern or "").strip()
    if not any([perm_f, tool_f, pat_f]):
        return "请指定 permission / tool / pattern 中的至少一项过滤"
    data = _load(sk)
    before = [r for r in (data.get("always") or []) if isinstance(r, dict)]
    after: list[dict[str, Any]] = []
    for r in before:
        if perm_f and str(r.get("permission") or "") != perm_f:
            after.append(r)
            continue
        if tool_f and str(r.get("tool") or "") != tool_f:
            after.append(r)
            continue
        if pat_f and str(r.get("pattern") or "") != pat_f:
            after.append(r)
            continue
    if len(after) == len(before):
        return (
            f"未找到匹配项 (permission={perm_f or '*'}, tool={tool_f or '*'}, "
            f"pattern={pat_f or '*'})"
        )
    data["always"] = after
    _save(sk, data)
    return f"已撤销 {len(before) - len(after)} 项始终允许"


def clear_always(session_key: str) -> str:
    """Sprint 24 P1-3.2: 清空 session 的所有 always 记录."""
    sk = str(session_key or "").strip()
    if not sk:
        return "无有效会话"
    data = _load(sk)
    count = len([r for r in (data.get("always") or []) if isinstance(r, dict)])
    data["always"] = []
    _save(sk, data)
    return f"已清除 {count} 项始终允许"


def summarize_approvals(session_key: str) -> dict[str, Any]:
    """Sprint 24 P1-3.2: 给 /诊断用的 always/once/pending 统计.

    Sprint 27 P1-3.3: 加 external_directory_always_count / external_directory_once_count
    字段, 给 /诊断 透传 external_directory 决策用. 旧调用方不受影响 (新字段默认 0).
    """
    sk = str(session_key or "").strip()
    if not sk:
        return {
            "always_count": 0,
            "once_active_count": 0,
            "has_pending": False,
            "external_directory_always_count": 0,
            "external_directory_once_count": 0,
        }
    data = _load(sk)
    always_list = [r for r in (data.get("always") or []) if isinstance(r, dict)]
    once_active = _purge_once(data.get("once") or [])
    always_count = len(always_list)
    once_active_count = len(once_active)
    ext_always = sum(
        1 for r in always_list if str(r.get("permission") or "") == "external_directory"
    )
    ext_once = sum(
        1 for r in once_active if str(r.get("permission") or "") == "external_directory"
    )
    pending = data.get("pending")
    has_pending = isinstance(pending, dict) and bool(pending.get("fingerprint"))
    return {
        "always_count": always_count,
        "once_active_count": once_active_count,
        "has_pending": has_pending,
        "external_directory_always_count": ext_always,
        "external_directory_once_count": ext_once,
    }
