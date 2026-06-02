"""Local durable outbox for gateway completion/supplementary messages."""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any, Iterator

from butler.config import get_butler_home
from butler.env_parse import env_truthy
from butler.io.atomic_write import atomic_write_text


def durable_outbox_enabled() -> bool:
    return env_truthy("BUTLER_GATEWAY_DURABLE_OUTBOX", default=True)


def durable_outbox_max_entries() -> int:
    raw = os.getenv("BUTLER_GATEWAY_DURABLE_OUTBOX_MAX", "").strip()
    if not raw:
        return 200
    try:
        return max(10, int(raw))
    except ValueError:
        return 200


def _outbox_root() -> Path:
    return get_butler_home() / "gateway_outbox"


def _state_dir(state: str) -> Path:
    path = _outbox_root() / state
    path.mkdir(parents=True, exist_ok=True)
    return path


def _entry_path(state: str, entry_id: str) -> Path:
    return _state_dir(state) / f"{entry_id}.json"


def _write_entry(path: Path, row: dict[str, Any]) -> None:
    """Serialize row to JSON and write atomically (fsync + no symlink).

    Sprint 9 REL-9: 原实现裸 ``path.write_text``，缺 fsync（崩溃丢数据）
    与 O_NOFOLLOW（可写到 symlink 目标绕过路径守门）。改为复用
    ``butler.io.atomic_write_text``。
    """
    text = json.dumps(row, ensure_ascii=False, indent=2)
    atomic_write_text(path, text)


def _trim_state_dir(state: str) -> None:
    path = _state_dir(state)
    files = sorted(path.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    keep = durable_outbox_max_entries()
    for extra in files[keep:]:
        extra.unlink(missing_ok=True)


@contextlib.contextmanager
def _outbox_read_lock() -> Iterator[None]:
    """Acquire ``flock(LOCK_SH)`` on the outbox lock file for the read window.

    Sprint 8 REL-2: cross-process readers (``list_pending_outbox`` /
    ``outbox_counts``) hold a shared lock so concurrent writers cannot
    leave a torn JSON file mid-replace.  Writers use ``LOCK_EX`` and
    release in the same call.
    """
    lock_path = _outbox_root() / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_SH)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


@contextlib.contextmanager
def _outbox_write_lock() -> Iterator[None]:
    """Acquire ``flock(LOCK_EX)`` on the outbox lock file for the write window.

    Sprint 9 REL-9: cross-process writers (``enqueue_outbox_message`` /
    ``_transition_outbox_entry``) hold an exclusive lock so concurrent
    writers (same or different process) cannot interleave write+replace
    and leave the on-disk state in a torn / racey state.  Readers use
    ``LOCK_SH`` and wait for our release.
    """
    lock_path = _outbox_root() / ".lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def enqueue_outbox_message(chat_id: str, body: str, *, kind: str) -> str:
    if not durable_outbox_enabled():
        return ""
    entry_id = uuid.uuid4().hex[:12]
    row = {
        "entry_id": entry_id,
        "chat_id": str(chat_id or "").strip(),
        "kind": str(kind or "completion").strip(),
        "body": str(body or "")[:4000],
        "status": "pending",
        "attempts": 0,
        "created_at": time.time(),
    }
    with _outbox_write_lock():
        _write_entry(_entry_path("pending", entry_id), row)
        _trim_state_dir("pending")
    return entry_id


def _transition_outbox_entry(entry_id: str, *, target_state: str, error: str = "") -> bool:
    if not entry_id or not durable_outbox_enabled():
        return False
    pending = _entry_path("pending", entry_id)
    if not pending.is_file():
        return False
    try:
        row = json.loads(pending.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    if not isinstance(row, dict):
        return False
    row["attempts"] = int(row.get("attempts") or 0) + 1
    row["status"] = target_state
    row[f"{target_state}_at"] = time.time()
    if error:
        row["error"] = str(error)[:500]
    target = _entry_path(target_state, entry_id)
    with _outbox_write_lock():
        _write_entry(pending, row)
        pending.replace(target)
        _trim_state_dir(target_state)
    return True


def mark_outbox_sent(entry_id: str) -> bool:
    return _transition_outbox_entry(entry_id, target_state="sent")


def mark_outbox_failed(entry_id: str, *, error: str = "") -> bool:
    return _transition_outbox_entry(entry_id, target_state="failed", error=error)


def list_pending_outbox() -> list[dict[str, Any]]:
    """Return all pending outbox entries (for startup replay).

    Sprint 8 REL-2: holds ``flock(LOCK_SH)`` for the read window so
    concurrent writers (mark_sent / mark_failed) cannot leave a torn
    JSON file mid-replace.  Writers are expected to acquire
    ``LOCK_EX`` for the duration of their write + replace.
    """
    if not durable_outbox_enabled():
        return []
    with _outbox_read_lock():
        entries: list[dict[str, Any]] = []
        for path in sorted(_state_dir("pending").glob("*.json"), key=lambda p: p.stat().st_mtime):
            try:
                row = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(row, dict):
                    entries.append(row)
            except (OSError, json.JSONDecodeError):
                continue
        return entries


def outbox_counts(*, chat_id: str = "") -> dict[str, int]:
    """Return per-state counts.  Sprint 8 REL-2: holds ``LOCK_SH``."""
    cid = str(chat_id or "").strip()
    counts = {"pending": 0, "sent": 0, "failed": 0}
    with _outbox_read_lock():
        for state in tuple(counts.keys()):
            for path in _state_dir(state).glob("*.json"):
                try:
                    row = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if cid and str(row.get("chat_id") or "").strip() != cid:
                    continue
                counts[state] += 1
    return counts


__all__ = [
    "durable_outbox_enabled",
    "durable_outbox_max_entries",
    "enqueue_outbox_message",
    "list_pending_outbox",
    "mark_outbox_failed",
    "mark_outbox_sent",
    "outbox_counts",
]
