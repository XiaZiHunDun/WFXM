"""Thread-safe cross-agent file read/write coordination (process-wide singleton).

Tracks per-task read timestamps and global last-writer metadata so concurrent
agents can detect stale edits. No external Hermes imports.
"""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

ReadStamp = Tuple[float, float, bool]  # (mtime, read_ts, partial)
_MAX_PATHS_PER_AGENT = 4096
_MAX_GLOBAL_WRITERS = 4096


def _disabled() -> bool:
    return os.environ.get("BUTLER_DISABLE_FILE_STATE_GUARD", "").strip() == "1"


def _resolved(path: str | Path) -> str:
    try:
        return str(Path(path).resolve())
    except OSError:
        return str(Path(path))


def _cap_dict(d: dict, limit: int) -> None:
    over = len(d) - limit
    if over <= 0:
        return
    it = iter(d)
    for _ in range(over):
        try:
            d.pop(next(it))
        except (StopIteration, KeyError):
            break


def _fmt_ts(ts: float) -> str:
    return time.strftime("%H:%M:%S", time.localtime(ts))


class FileStateRegistry:
    """Process-wide coordinator for cross-agent file edits."""

    def __init__(self) -> None:
        self._reads: Dict[str, Dict[str, ReadStamp]] = defaultdict(dict)
        self._last_writer: Dict[str, Tuple[str, float]] = {}
        self._path_locks: Dict[str, threading.Lock] = {}
        self._meta_lock = threading.Lock()
        self._state_lock = threading.Lock()

    def _lock_for(self, resolved: str) -> threading.Lock:
        with self._meta_lock:
            lock = self._path_locks.get(resolved)
            if lock is None:
                lock = threading.Lock()
                self._path_locks[resolved] = lock
            return lock

    @contextmanager
    def lock_path(self, resolved: str):
        lock = self._lock_for(resolved)
        lock.acquire()
        try:
            yield
        finally:
            lock.release()

    def record_read(
        self,
        task_id: str,
        resolved: str,
        *,
        partial: bool = False,
        mtime: float | None = None,
    ) -> None:
        if _disabled():
            return
        if mtime is None:
            try:
                mtime = os.path.getmtime(resolved)
            except OSError:
                return
        now = time.time()
        with self._state_lock:
            agent_reads = self._reads[task_id]
            agent_reads[resolved] = (float(mtime), now, bool(partial))
            _cap_dict(agent_reads, _MAX_PATHS_PER_AGENT)

    def note_write(
        self,
        task_id: str,
        resolved: str,
        *,
        mtime: float | None = None,
    ) -> None:
        """Record a successful write: update global last-writer and this agent's read stamp."""
        if _disabled():
            return
        if mtime is None:
            try:
                mtime = os.path.getmtime(resolved)
            except OSError:
                return
        now = time.time()
        with self._state_lock:
            self._last_writer[resolved] = (task_id, now)
            _cap_dict(self._last_writer, _MAX_GLOBAL_WRITERS)
            self._reads[task_id][resolved] = (float(mtime), now, False)
            _cap_dict(self._reads[task_id], _MAX_PATHS_PER_AGENT)

    def check_stale(self, task_id: str, resolved: str) -> str | None:
        """Return a human-readable staleness warning, or ``None`` if the write looks safe."""
        if _disabled():
            return None
        with self._state_lock:
            stamp = self._reads.get(task_id, {}).get(resolved)
            last_writer = self._last_writer.get(resolved)

        if stamp is None and last_writer is None:
            return None

        try:
            current_mtime = os.path.getmtime(resolved)
        except OSError:
            return None

        if last_writer is not None:
            writer_tid, writer_ts = last_writer
            if writer_tid != task_id:
                if stamp is None:
                    return (
                        f"{resolved} was modified by sibling subagent "
                        f"{writer_tid!r} but this agent never read it. "
                        "Read the file before writing to avoid overwriting "
                        "the sibling's changes."
                    )
                read_ts = stamp[1]
                if writer_ts > read_ts:
                    return (
                        f"{resolved} was modified by sibling subagent "
                        f"{writer_tid!r} at {_fmt_ts(writer_ts)} — after "
                        f"this agent's last read at {_fmt_ts(read_ts)}. "
                        "Re-read the file before writing."
                    )

        if stamp is not None:
            read_mtime, _read_ts, partial = stamp
            if current_mtime != read_mtime:
                return (
                    f"{resolved} was modified since you last read it "
                    "on disk (external edit or unrecorded writer). "
                    "Re-read the file before writing."
                )
            if partial:
                return (
                    f"{resolved} was last read with offset/limit pagination "
                    "(partial view). Re-read the whole file before "
                    "overwriting it."
                )

        if stamp is None:
            return (
                f"{resolved} was not read by this agent. "
                "Read the file first so you can write an informed edit."
            )

        return None

    def writes_since(
        self,
        exclude_task_id: str,
        since_ts: float,
        paths: Iterable[str],
    ) -> Dict[str, List[str]]:
        paths_set = set(paths)
        out: Dict[str, List[str]] = defaultdict(list)
        if _disabled():
            return {}
        with self._state_lock:
            for p, (writer_tid, ts) in self._last_writer.items():
                if writer_tid == exclude_task_id:
                    continue
                if ts < since_ts:
                    continue
                if p in paths_set:
                    out[writer_tid].append(p)
        return dict(out)

    def known_reads(self, task_id: str) -> List[str]:
        if _disabled():
            return []
        with self._state_lock:
            return list(self._reads.get(task_id, {}).keys())

    def clear(self) -> None:
        with self._state_lock:
            self._reads.clear()
            self._last_writer.clear()
        with self._meta_lock:
            self._path_locks.clear()


_registry = FileStateRegistry()


def record_read(task_id: str, path: str | Path, *, partial: bool = False) -> None:
    _registry.record_read(task_id, _resolved(path), partial=partial)


def note_write(task_id: str, path: str | Path) -> None:
    _registry.note_write(task_id, _resolved(path))


def check_stale(task_id: str, path: str | Path) -> str | None:
    return _registry.check_stale(task_id, _resolved(path))


def lock_path(path: str | Path):
    return _registry.lock_path(_resolved(path))


def writes_since(
    exclude_task_id: str,
    since_ts: float,
    paths: Iterable[str],
) -> Dict[str, List[str]]:
    resolved = [_resolved(p) for p in paths]
    return _registry.writes_since(exclude_task_id, since_ts, resolved)
