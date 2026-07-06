"""Session-scoped read-before-edit guard (Claude Code readFileState + mtime)."""

from __future__ import annotations

import hashlib
import os
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from butler.env_parse import env_truthy

_LOCK = threading.RLock()
_MAX_ENTRIES = 100
_MAX_SESSIONS = 512
_MAX_CONTENT_BYTES = 25 * 1024 * 1024
_BY_SESSION: dict[str, OrderedDict[str, "ReadStateEntry"]] = {}
_RECENT_EDITS: dict[str, list[str]] = {}


def _evict_oldest_session_locked(store: dict[str, Any], *, keep: str) -> None:
    while len(store) >= _MAX_SESSIONS and keep not in store:
        store.pop(next(iter(store)))


@dataclass(frozen=True)
class ReadStateEntry:
    path: str
    mtime_ns: int
    size: int
    content_hash: str
    read_turn: int
    is_partial_view: bool = False


def read_before_edit_enabled() -> bool:
    return bool(env_truthy("BUTLER_READ_BEFORE_EDIT", default=True))


def read_state_max_entries() -> int:
    try:
        from butler.env_parse import int_env

        return int(int_env("BUTLER_READ_STATE_MAX_ENTRIES", _MAX_ENTRIES, min=10))
    except ValueError:
        return _MAX_ENTRIES


def normalize_quotes(text: str) -> str:
    """Map curly quotes to ASCII for fuzzy patch matching."""
    return (
        text.replace("\u201c", '"')
        .replace("\u201d", '"')
        .replace("\u2018", "'")
        .replace("\u2019", "'")
    )


def _session_key(explicit: str | None = None) -> str:
    if explicit and str(explicit).strip():
        return str(explicit).strip()
    from butler.execution_context import get_audit_session_key

    return str(get_audit_session_key(fallback="_global"))


def _evict_lru(store: OrderedDict[str, ReadStateEntry]) -> None:
    limit = read_state_max_entries()
    while len(store) > limit:
        store.popitem(last=False)


def reset_read_state(session_key: str | None = None) -> None:
    with _LOCK:
        if session_key is None:
            _BY_SESSION.clear()
            _RECENT_EDITS.clear()
            return
        sk = _session_key(session_key)
        _BY_SESSION.pop(sk, None)
        _RECENT_EDITS.pop(sk, None)


def record_read_state(
    resolved_path: Path,
    stat_result: os.stat_result,
    content: bytes,
    *,
    session_key: str | None = None,
    is_partial_view: bool = False,
) -> ReadStateEntry:
    """Record a successful read_file for later patch/write validation."""
    if len(content) > _MAX_CONTENT_BYTES:
        is_partial_view = True
    path_key = str(resolved_path.resolve())
    with _LOCK:
        sk = _session_key(session_key)
        if sk not in _BY_SESSION:
            _evict_oldest_session_locked(_BY_SESSION, keep=sk)
            _BY_SESSION[sk] = OrderedDict()
        store = _BY_SESSION[sk]
        turn = len(store) + 1
        entry = ReadStateEntry(
            path=path_key,
            mtime_ns=_mtime_ns(stat_result),
            size=int(stat_result.st_size),
            content_hash=_content_hash(content),
            read_turn=turn,
            is_partial_view=is_partial_view,
        )
        if path_key in store:
            store.move_to_end(path_key)
        store[path_key] = entry
        _evict_lru(store)
    return entry


def record_partial_view_path(path: str | os.PathLike[str], *, session_key: str | None = None) -> None:
    """Mark auto-injected content as partial (edit blocked until full read)."""
    resolved = Path(path).resolve()
    try:
        st = resolved.stat()
    except OSError:
        return
    record_read_state(
        resolved,
        st,
        b"",
        session_key=session_key,
        is_partial_view=True,
    )


def record_edit_path(path: str | os.PathLike[str], *, session_key: str | None = None) -> None:
    """Track recently modified paths for post-compact re-attachment."""
    sk = _session_key(session_key)
    path_key = str(Path(path).resolve())
    with _LOCK:
        if sk not in _RECENT_EDITS:
            _evict_oldest_session_locked(_RECENT_EDITS, keep=sk)
        recent = _RECENT_EDITS.setdefault(sk, [])
        if path_key in recent:
            recent.remove(path_key)
        recent.append(path_key)
        del recent[:-5]


def get_recent_edit_paths(*, session_key: str | None = None, limit: int = 5) -> list[str]:
    sk = _session_key(session_key)
    with _LOCK:
        return list(_RECENT_EDITS.get(sk, [])[-limit:])


def _parent_delegate_session_key(session_key: str) -> str | None:
    """Parent session key for ``{parent}::delegate::{task_id}`` child sessions."""
    sk = str(session_key or "").strip()
    marker = "::delegate::"
    if marker not in sk:
        return None
    parent = sk.split(marker, 1)[0].strip()
    return parent if parent and parent != sk else None


def get_read_state(resolved_path: Path, *, session_key: str | None = None) -> ReadStateEntry | None:
    path_key = str(resolved_path.resolve())
    with _LOCK:
        sk = _session_key(session_key)
        entry = _lookup_read_state_locked(path_key, sk)
        if entry is not None:
            return entry
        parent_sk = _parent_delegate_session_key(sk)
        if parent_sk:
            return _lookup_read_state_locked(path_key, parent_sk)
        return None


def _lookup_read_state_locked(path_key: str, sk: str) -> ReadStateEntry | None:
    store = _BY_SESSION.get(sk)
    if store is None:
        return None
    entry = store.get(path_key)
    if entry is not None:
        store.move_to_end(path_key)
    return entry


def _mtime_ns(st: os.stat_result) -> int:
    ns = getattr(st, "st_mtime_ns", None)
    if ns is not None:
        return int(ns)
    return int(st.st_mtime * 1_000_000_000)


def _content_hash(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _stat_matches(entry: ReadStateEntry, current: os.stat_result) -> bool:
    if (entry.size, entry.mtime_ns) != (int(current.st_size), _mtime_ns(current)):
        return False
    return True


def read_state_hint(code: str) -> str:
    """Actionable hint for read-before-edit guard codes."""
    return {
        "READ_STATE_REQUIRED": (
            "Call read_file on this path first, then patch/write with content copied "
            "exactly from that output (whitespace and quotes matter)."
        ),
        "READ_STATE_PARTIAL_VIEW": (
            "read_file the full file without offset/limit, then edit."
        ),
        "READ_STATE_STALE": (
            "File changed since read_file — read_file again, then retry patch."
        ),
        "READ_STATE_NOT_FILE": "read-before-edit applies to regular files only.",
        "READ_STATE_STAT_FAILED": "Could not stat file; verify path with list_directory.",
    }.get(code, "")


def _guard_payload(code: str, error: str, path: str, **extra: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {"ok": False, "error": error, "code": code, "path": path}
    hint = read_state_hint(code)
    if hint:
        payload["hint"] = hint
    payload.update(extra)
    return payload


def check_read_state_for_resolved(resolved: Path) -> dict[str, Any] | None:
    """Validate read state for an already-resolved path (no workspace re-check)."""
    if not read_before_edit_enabled():
        return None
    if not resolved.exists():
        return None
    if not resolved.is_file():
        return _guard_payload(
            "READ_STATE_NOT_FILE",
            "read-before-edit 仅适用于普通文件",
            str(resolved),
        )

    entry = get_read_state(resolved)
    if entry is None:
        return _guard_payload(
            "READ_STATE_REQUIRED",
            "必须先调用 read_file 读取该文件后再编辑",
            str(resolved),
        )

    if entry.is_partial_view:
        return _guard_payload(
            "READ_STATE_PARTIAL_VIEW",
            "当前为部分视图（如自动注入摘要），请 read_file 完整读取后再编辑",
            str(resolved),
        )

    try:
        current = resolved.stat()
    except OSError as exc:
        return _guard_payload(
            "READ_STATE_STAT_FAILED",
            str(exc),
            str(resolved),
        )

    if not _stat_matches(entry, current):
        try:
            disk = resolved.read_bytes()
            if not entry.is_partial_view and _content_hash(disk) == entry.content_hash:
                return None
        except OSError:
            pass
        return _guard_payload(
            "READ_STATE_STALE",
            "文件在 read_file 之后已被外部修改，请重新 read_file 后再编辑",
            str(resolved),
            read_mtime_ns=entry.mtime_ns,
            current_mtime_ns=_mtime_ns(current),
        )
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


def rehydrate_read_state_from_messages(
    messages: list[dict[str, Any]],
    *,
    session_key: str | None = None,
) -> int:
    """Best-effort: record paths mentioned in past read_file tool results."""
    count = 0
    for msg in messages:
        if msg.get("role") != "tool":
            continue
        content = str(msg.get("content") or "")
        if "read_file" not in content.lower() and not content.strip().startswith("/"):
            continue
        for line in content.splitlines()[:3]:
            candidate = line.strip().split(":", 1)[0].strip()
            if candidate.startswith("/") or candidate.startswith("."):
                p = Path(candidate)
                if p.is_file():
                    try:
                        data = p.read_bytes()[:_MAX_CONTENT_BYTES]
                        record_read_state(p, p.stat(), data, session_key=session_key)
                        count += 1
                    except OSError:
                        continue
    return count


def read_state_summary(*, session_key: str | None = None) -> dict[str, Any]:
    with _LOCK:
        sk = _session_key(session_key)
        store = _BY_SESSION.get(sk)
        if store is None:
            return {"tracked_files": 0, "paths": [], "partial_views": 0}
        return {
            "tracked_files": len(store),
            "paths": list(store.keys())[:5],
            "partial_views": sum(1 for e in store.values() if e.is_partial_view),
        }
