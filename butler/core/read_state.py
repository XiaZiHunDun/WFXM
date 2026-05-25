"""Session-scoped read-before-edit guard (Claude Code readFileState + mtime)."""

from __future__ import annotations

import hashlib
import os
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy

_LOCK = threading.RLock()
_BY_SESSION: dict[str, dict[str, "ReadStateEntry"]] = {}


@dataclass(frozen=True)
class ReadStateEntry:
    path: str
    mtime_ns: int
    size: int
    content_hash: str
    read_turn: int


def read_before_edit_enabled() -> bool:
    return env_truthy("BUTLER_READ_BEFORE_EDIT", default=True)


def normalize_quotes(text: str) -> str:
    """Map curly quotes to ASCII for fuzzy patch matching."""
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _session_key() -> str:
    from butler.execution_context import get_audit_session_key

    return get_audit_session_key(fallback="_global")


def _mtime_ns(st: os.stat_result) -> int:
    ns = getattr(st, "st_mtime_ns", None)
    if ns is not None:
        return int(ns)
    return int(st.st_mtime * 1_000_000_000)


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _bucket(session_key: str | None = None) -> dict[str, ReadStateEntry]:
    key = str(session_key or "").strip() or _session_key()
    with _LOCK:
        return _BY_SESSION.setdefault(key, {})


def reset_read_state(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _BY_SESSION.clear()
            return
        sk = str(session_key or "").strip() or "_global"
        _BY_SESSION.pop(sk, None)


def record_read_state(
    resolved_path: Path,
    stat_result: os.stat_result,
    content: bytes,
    *,
    session_key: str | None = None,
) -> ReadStateEntry:
    """Record a successful read_file for later patch/write validation."""
    path_key = str(resolved_path.resolve())
    store = _bucket(session_key)
    turn = sum(1 for _ in store) + 1
    entry = ReadStateEntry(
        path=path_key,
        mtime_ns=_mtime_ns(stat_result),
        size=int(stat_result.st_size),
        content_hash=_content_hash(content),
        read_turn=turn,
    )
    with _LOCK:
        store[path_key] = entry
    return entry


def get_read_state(resolved_path: Path, *, session_key: str | None = None) -> ReadStateEntry | None:
    path_key = str(resolved_path.resolve())
    return _bucket(session_key).get(path_key)


def _stat_matches(entry: ReadStateEntry, current: os.stat_result) -> bool:
    if (entry.size, entry.mtime_ns) != (int(current.st_size), _mtime_ns(current)):
        return False
    return True


def check_read_state_for_resolved(resolved: Path) -> dict[str, Any] | None:
    """Validate read state for an already-resolved path (no workspace re-check)."""
    if not read_before_edit_enabled():
        return None
    if not resolved.exists():
        return None
    if not resolved.is_file():
        return {
            "ok": False,
            "error": "read-before-edit 仅适用于普通文件",
            "code": "READ_STATE_NOT_FILE",
            "path": str(resolved),
        }

    entry = get_read_state(resolved)
    if entry is None:
        return {
            "ok": False,
            "error": "必须先调用 read_file 读取该文件后再编辑",
            "code": "READ_STATE_REQUIRED",
            "path": str(resolved),
        }

    try:
        current = resolved.stat()
    except OSError as exc:
        return {
            "ok": False,
            "error": str(exc),
            "code": "READ_STATE_STAT_FAILED",
            "path": str(resolved),
        }

    if not _stat_matches(entry, current):
        return {
            "ok": False,
            "error": "文件在 read_file 之后已被外部修改，请重新 read_file 后再编辑",
            "code": "READ_STATE_STALE",
            "path": str(resolved),
            "read_mtime_ns": entry.mtime_ns,
            "current_mtime_ns": _mtime_ns(current),
        }
    return None


def require_read_before_edit(
    path: str | os.PathLike[str],
    *,
    for_write: bool = False,
) -> dict[str, Any] | None:
    """Return an error payload dict when edit must be blocked; None if allowed."""
    if not read_before_edit_enabled():
        return None

    from butler.tools.path_safety import check_tool_path

    safety = check_tool_path(path, for_write=for_write)
    if not safety.allowed:
        return None
    return check_read_state_for_resolved(safety.path)


def read_state_summary(*, session_key: str | None = None) -> dict[str, Any]:
    store = _bucket(session_key)
    return {"tracked_files": len(store), "paths": list(store.keys())[:5]}
