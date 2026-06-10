"""Lightweight LLM response cache by prompt fingerprint.

History:
  - PR-X5 / MetaGPT subset: initial dict-based cache.
  - Sprint 11 PERF-11-2/3: per-path in-memory cache (avoid repeat file IO).
  - R1-11 (this revision, PR-1): dataclass-encapsulated state, LRU
    semantics, TTL via ``BUTLER_EXP_CACHE_TTL_SECONDS``, multi-process
    file lock on POSIX (``fcntl``) / Windows (``msvcrt``).

Module-level mutable state has been moved into ``CacheBackend``; the
default backend is a process-wide singleton returned by
``get_default_backend()``.  The 3 public functions
(``fingerprint_llm_request``, ``lookup_cached_response``,
``store_cached_response``) keep their signatures so the 2 callers in
``butler/core/llm_retry.py`` require zero changes.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import sys
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from butler.core.meta_flags import exp_cache_enabled
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

# --- defaults ----------------------------------------------------------------

# Sprint 11 PERF-11-3: 500 entries per file path.
_DEFAULT_MAX_ENTRIES = 500
_MAX_ENTRIES_CEILING = 5000
_MAX_ENTRIES_FLOOR = 10

# R1-11: TTL prevents stale caches from living forever; 7 days default.
_DEFAULT_TTL_SECONDS = 7 * 24 * 3600.0


# --- public fingerprint ------------------------------------------------------

def fingerprint_llm_request(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict] | None = None,
) -> str:
    """Stable fingerprint: provider+model+last user content+sorted tool names."""
    last_user = ""
    for msg in reversed(messages):
        if str(msg.get("role") or "") == "user":
            last_user = str(msg.get("content") or "")[:4000]
            break
    tool_names = sorted(
        str(t.get("function", {}).get("name") or t.get("name") or "")
        for t in (tools or [])
        if isinstance(t, dict)
    )
    payload = {
        "provider": provider or "",
        "model": model or "",
        "user": last_user,
        "tools": tool_names[:80],
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


# --- R1-11: encapsulated state ------------------------------------------------

@dataclass
class CacheEntry:
    """One cached LLM response.

    ``created_at`` is wall-clock seconds; used by ``CacheBackend`` for
    TTL expiry.  On disk load, missing/garbled ``created_at`` falls back
    to ``time.time()`` (treat as fresh).
    """
    content: str
    provider: str
    model: str
    created_at: float = field(default_factory=time.time)


@dataclass
class CacheBackend:
    """R1-11: encapsulated state for the LLM response cache.

    Holds per-path LRU (``OrderedDict``) + per-path load flag + size +
    TTL config.  All mutations guarded by ``_lock`` (RLock; reentrant).
    Public functions operate on the default backend returned by
    ``get_default_backend()``.
    """
    max_entries: int = _DEFAULT_MAX_ENTRIES
    ttl_seconds: float = _DEFAULT_TTL_SECONDS
    _lock: threading.RLock = field(
        default_factory=threading.RLock, repr=False, compare=False
    )
    _path_caches: dict[str, OrderedDict[str, CacheEntry]] = field(
        default_factory=dict, repr=False, compare=False
    )
    _loaded_paths: set[str] = field(
        default_factory=set, repr=False, compare=False
    )

    # --- introspection --------------------------------------------------

    def is_loaded(self, path_key: str) -> bool:
        with self._lock:
            return path_key in self._loaded_paths

    def size(self, path_key: str) -> int:
        with self._lock:
            cache = self._path_caches.get(path_key)
            return len(cache) if cache is not None else 0

    # --- core operations -------------------------------------------------

    def get(self, path_key: str, fp: str) -> CacheEntry | None:
        """LRU-touch + TTL check; return None if missing or expired.

        Side effect: on hit, the entry is moved to the back of the
        OrderedDict (most-recently-used position).
        """
        with self._lock:
            cache = self._path_caches.get(path_key)
            if cache is None:
                return None
            entry = cache.get(fp)
            if entry is None:
                return None
            if self._is_expired(entry):
                cache.pop(fp, None)
                return None
            cache.move_to_end(fp)
            return entry

    def put(self, path_key: str, fp: str, entry: CacheEntry) -> None:
        """Insert/refresh entry; LRU-evict from front when over capacity."""
        with self._lock:
            cache = self._path_caches.setdefault(path_key, OrderedDict())
            cache[fp] = entry
            cache.move_to_end(fp)
            while len(cache) > self.max_entries:
                cache.popitem(last=False)

    # --- helpers ---------------------------------------------------------

    def _is_expired(self, entry: CacheEntry) -> bool:
        if self.ttl_seconds <= 0:
            return False
        return (time.time() - entry.created_at) > self.ttl_seconds


# --- module singleton + env-driven config ------------------------------------

_DEFAULT_BACKEND: CacheBackend | None = None
_DEFAULT_BACKEND_LOCK = threading.Lock()


def get_default_backend() -> CacheBackend:
    """Module-level singleton; constructed lazily with env-driven config."""
    global _DEFAULT_BACKEND
    if _DEFAULT_BACKEND is None:
        with _DEFAULT_BACKEND_LOCK:
            if _DEFAULT_BACKEND is None:
                _DEFAULT_BACKEND = CacheBackend(
                    max_entries=_resolve_max_entries(),
                    ttl_seconds=_resolve_ttl_seconds(),
                )
    return _DEFAULT_BACKEND


def reset_default_backend(backend: CacheBackend | None = None) -> None:
    """Test/runtime hook: replace the default backend singleton.

    Pass ``None`` to clear — next ``get_default_backend()`` call will
    reconstruct from env.  Tests use this between cases to avoid state
    leakage.
    """
    global _DEFAULT_BACKEND
    with _DEFAULT_BACKEND_LOCK:
        _DEFAULT_BACKEND = backend


def _resolve_max_entries() -> int:
    from butler.env_parse import int_env

    raw = int_env("BUTLER_EXP_CACHE_MAX", _DEFAULT_MAX_ENTRIES)
    return max(_MAX_ENTRIES_FLOOR, min(_MAX_ENTRIES_CEILING, raw))


def _resolve_ttl_seconds() -> float:
    try:
        raw = int(
            os.getenv("BUTLER_EXP_CACHE_TTL_SECONDS", str(int(_DEFAULT_TTL_SECONDS)))
        )
    except ValueError:
        return float(_DEFAULT_TTL_SECONDS)
    if raw <= 0:
        return 0.0
    return float(raw)


# --- back-compat shims (preserved for tests that monkeypatch them) -----------

def _cache_enabled() -> bool:
    return exp_cache_enabled()


def _resolve_cache_path() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is not None:
            from butler.execution_context import get_current_session_key

            proj = pm.get_current(session_key=str(get_current_session_key() or ""))
            if proj is not None:
                return (
                    Path(proj.workspace).expanduser().resolve()
                    / ".butler"
                    / "experiences"
                    / "llm_cache.jsonl"
                )
    except Exception as exc:
        logger.debug("resolve cache path skipped: %s", exc)
    home = Path.home() / ".butler" / "experiences" / "llm_cache.jsonl"
    return home


# --- disk I/O under file lock ------------------------------------------------

def _acquire_lock(fd: int) -> bool:
    """Acquire exclusive lock on ``fd``; return True if locked, False on no-op."""
    if sys.platform == "win32":
        try:
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_LOCK, 1)
            return True
        except (ImportError, OSError) as exc:
            logger.debug("msvcrt file lock unavailable: %s", exc)
            return False
    try:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_EX)
        return True
    except (ImportError, OSError) as exc:
        logger.debug("fcntl file lock unavailable: %s", exc)
        return False


def _release_lock(fd: int) -> None:
    """Best-effort release of lock on ``fd``; never raises."""
    try:
        if sys.platform == "win32":
            import msvcrt

            os.lseek(fd, 0, os.SEEK_SET)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        else:
            import fcntl

            fcntl.flock(fd, fcntl.LOCK_UN)
    except (ImportError, OSError) as exc:
        logger.debug("file unlock failed: %s", exc)


@contextlib.contextmanager
def _file_lock(path: Path) -> Iterator[None]:
    """Best-effort exclusive lock on sidecar ``.lock`` file.

    POSIX: ``fcntl.flock(LOCK_EX)``.  Windows: ``msvcrt.locking(LK_LOCK, 1)``.
    Falls back to no-op on platforms without either — cache stays
    correct for in-process use; cross-process races may still occur.
    Cache failures are best-effort and never raise to the caller.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd: int | None = None
    locked = False
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
        locked = _acquire_lock(fd)
        yield
    finally:
        if fd is not None:
            if locked:
                _release_lock(fd)
            try:
                os.close(fd)
            except OSError:
                pass


def _lock_path_for(path: Path) -> Path:
    return path.with_name(path.name + ".lock")


def _read_disk_rows(path: Path) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    if not path.is_file():
        return out
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict) and row.get("fp"):
                out[str(row["fp"])] = row
    except OSError as exc:
        logger.debug("exp_cache read %s: %s", path, exc)
    return out


def _row_to_entry(row: dict[str, Any]) -> CacheEntry:
    raw_ts = row.get("created_at")
    try:
        created_at = float(raw_ts) if raw_ts is not None else time.time()
    except (TypeError, ValueError):
        created_at = time.time()
    return CacheEntry(
        content=str(row.get("content") or ""),
        provider=str(row.get("provider") or ""),
        model=str(row.get("model") or ""),
        created_at=created_at,
    )


def _ensure_path_loaded(path: Path, backend: CacheBackend) -> None:
    """Idempotent: load disk rows into ``backend._path_caches[path_key]``."""
    path_key = str(path)
    if backend.is_loaded(path_key):
        return
    with backend._lock:
        if backend.is_loaded(path_key):
            return
        with _file_lock(_lock_path_for(path)):
            disk_rows = _read_disk_rows(path)
            cache: OrderedDict[str, CacheEntry] = OrderedDict()
            for fp, row in disk_rows.items():
                cache[fp] = _row_to_entry(row)
            while len(cache) > backend.max_entries:
                cache.popitem(last=False)
            backend._path_caches[path_key] = cache
            backend._loaded_paths.add(path_key)


def _persist_path(path: Path, backend: CacheBackend) -> None:
    """Write backend's in-memory cache for ``path`` to disk under file lock."""
    path_key = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with backend._lock:
        cache = backend._path_caches.get(path_key)
        items: list[dict[str, Any]] = []
        if cache is not None:
            for fp, entry in cache.items():
                items.append(
                    {
                        "fp": fp,
                        "content": entry.content,
                        "provider": entry.provider,
                        "model": entry.model,
                        "created_at": entry.created_at,
                    }
                )
        with _file_lock(_lock_path_for(path)):
            text = "\n".join(
                json.dumps(it, ensure_ascii=False) for it in items
            ) + ("\n" if items else "")
            try:
                from butler.io.atomic_write import atomic_write_text

                atomic_write_text(path, text)
            except Exception:
                path.write_text(text, encoding="utf-8")


# --- public API --------------------------------------------------------------

def lookup_cached_response(fp: str) -> str | None:
    """Return cached LLM response for fingerprint ``fp`` (or None on miss)."""
    if not _cache_enabled() or not fp:
        return None
    path = _resolve_cache_path()
    if path is None:
        return None
    backend = get_default_backend()
    _ensure_path_loaded(path, backend)
    entry = backend.get(str(path), fp)
    if entry is None:
        return None
    content = (entry.content or "").strip()
    return content or None


def store_cached_response(
    fp: str,
    content: str,
    *,
    provider: str = "",
    model: str = "",
) -> None:
    """Persist LLM response for fingerprint ``fp`` to cache."""
    if not _cache_enabled() or not fp or not str(content or "").strip():
        return
    if not env_truthy("BUTLER_EXP_CACHE_STORE", default=True):
        return
    path = _resolve_cache_path()
    if path is None:
        return
    entry = CacheEntry(
        content=str(content)[:16000],
        provider=provider,
        model=model,
    )
    backend = get_default_backend()
    _ensure_path_loaded(path, backend)
    backend.put(str(path), fp, entry)
    _persist_path(path, backend)


__all__ = [
    "CacheBackend",
    "CacheEntry",
    "fingerprint_llm_request",
    "get_default_backend",
    "lookup_cached_response",
    "reset_default_backend",
    "store_cached_response",
]
