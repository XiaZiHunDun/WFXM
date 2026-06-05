"""Pending skill install confirmations (WeChat Owner flow)."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterator

from butler.config import get_butler_home
from butler.io.atomic_write import atomic_write_text
from butler.io.safe_load import safe_load_json


@dataclass
class PendingSkillInstall:
    identifier: str
    name: str
    description: str
    source: str
    trust: str
    session_key: str
    platform: str
    external_id: str
    requested_at: float


def pending_ttl_seconds() -> int:
    try:
        return max(300, int(os.getenv("BUTLER_REGISTRY_PENDING_TTL", "1800")))
    except ValueError:
        return 1800


def _pending_path() -> Path:
    path = get_butler_home() / "registry-cache" / "pending-installs.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _load_all() -> dict[str, Any]:
    path = _pending_path()
    # Audit R2-19: corrupt pending-installs.json used to silently
    # drop every pending confirmation. safe_load renames the
    # corrupt file for forensic retention, logs WARNING with
    # exc_info, and records the event for /诊断.
    default_seed: dict[str, Any] = {"entries": {}}
    data = safe_load_json(path, default=default_seed, kind="registry_install_pending")
    if not isinstance(data, dict):
        return default_seed
    data.setdefault("entries", {})
    return data


def _save_all(data: dict[str, Any]) -> None:
    """Atomic JSON write (fsync + no symlink).  Sprint 9 REL-11 替换原裸 write_text。"""
    text = json.dumps(data, ensure_ascii=False, indent=2)
    atomic_write_text(_pending_path(), text)


@contextlib.contextmanager
def _write_lock() -> Iterator[None]:
    """Hold ``flock(LOCK_EX)`` so concurrent save/clear calls cannot interleave
    their read-modify-write cycle.  Sprint 9 REL-11 防止 save 互相覆盖。

    Sprint 10 REL-NEW-01: O_NOFOLLOW 拒 symlink bypass。
    """
    lock_path = _pending_path().parent / ".pending-installs.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    except OSError:
        raise
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _entry_key(session_key: str, platform: str, external_id: str | None) -> str:
    return f"{session_key}|{platform}|{external_id or ''}"


def _purge_expired(entries: dict[str, Any]) -> dict[str, Any]:
    now = time.time()
    ttl = pending_ttl_seconds()
    out: dict[str, Any] = {}
    for key, row in entries.items():
        if not isinstance(row, dict):
            continue
        ts = float(row.get("requested_at") or 0)
        if now - ts <= ttl:
            out[key] = row
    return out


def save_pending(row: PendingSkillInstall) -> None:
    with _write_lock():
        data = _load_all()
        entries = _purge_expired(data.get("entries") or {})
        key = _entry_key(row.session_key, row.platform, row.external_id)
        entries[key] = {
            "identifier": row.identifier,
            "name": row.name,
            "description": row.description[:500],
            "source": row.source,
            "trust": row.trust,
            "session_key": row.session_key,
            "platform": row.platform,
            "external_id": row.external_id,
            "requested_at": row.requested_at,
        }
        data["entries"] = entries
        _save_all(data)


def get_pending(
    *,
    session_key: str,
    platform: str,
    external_id: str | None,
    identifier: str = "",
) -> PendingSkillInstall | None:
    """Read pending install — **read-only**, no side effects.

    Sprint 9 REL-11：原实现末尾 _save_all 写盘清理过期项。这把"读"
    路径变成"读+写"，并发 save 互相覆盖、读后无谓写盘。修复：纯读；
    过期清理由 save_pending / clear_pending 写盘时顺带做。
    """
    data = _load_all()
    entries = data.get("entries") or {}

    ident = identifier.strip()
    key = _entry_key(session_key, platform, external_id)
    row = entries.get(key)
    if isinstance(row, dict):
        if ident and str(row.get("identifier") or "") != ident:
            return None
        return PendingSkillInstall(
            identifier=str(row.get("identifier") or ""),
            name=str(row.get("name") or ""),
            description=str(row.get("description") or ""),
            source=str(row.get("source") or ""),
            trust=str(row.get("trust") or "community"),
            session_key=str(row.get("session_key") or session_key),
            platform=str(row.get("platform") or platform),
            external_id=str(row.get("external_id") or (external_id or "")),
            requested_at=float(row.get("requested_at") or 0),
        )

    if ident:
        for row in entries.values():
            if isinstance(row, dict) and str(row.get("identifier") or "") == ident:
                return PendingSkillInstall(
                    identifier=ident,
                    name=str(row.get("name") or ""),
                    description=str(row.get("description") or ""),
                    source=str(row.get("source") or ""),
                    trust=str(row.get("trust") or "community"),
                    session_key=str(row.get("session_key") or session_key),
                    platform=str(row.get("platform") or platform),
                    external_id=str(row.get("external_id") or (external_id or "")),
                    requested_at=float(row.get("requested_at") or 0),
                )
    return None


def clear_pending(
    *,
    session_key: str,
    platform: str,
    external_id: str | None,
    identifier: str = "",
) -> None:
    with _write_lock():
        data = _load_all()
        entries = _purge_expired(data.get("entries") or {})
        key = _entry_key(session_key, platform, external_id)
        if key in entries:
            del entries[key]
        if identifier.strip():
            ident = identifier.strip()
            for k, row in list(entries.items()):
                if isinstance(row, dict) and str(row.get("identifier") or "") == ident:
                    del entries[k]
        data["entries"] = entries
        _save_all(data)


def format_pending_prompt(hit_name: str, identifier: str, source: str, trust: str) -> str:
    return (
        f"待确认安装: {hit_name} [{source}/{trust}]\n"
        f"id: {identifier}\n\n"
        f"请 Owner 回复:\n"
        f"  /确认安装 {identifier}\n"
        f"或: /技能 确认 {identifier}\n\n"
        f"取消: /技能 取消安装"
    )
