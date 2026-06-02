"""Shared per-(path, mtime) JSON file cache for tools.

Why:
    Tools like ``expense``/``contacts``/``habits`` repeatedly call ``_load_all()``
    within a single agent turn (e.g. ``summary`` + ``list`` + ``breakdown``).
    Each call does ``glob("*.json")`` + ``read_text`` + ``json.loads`` on every
    file. With N records and K calls per turn that's K×N disk reads.

How:
    Cache parsed JSON by ``(path, mtime_ns)``.
    - Hit on identical mtime → skip read+parse.
    - Mtime change → natural invalidation (handles cross-process writes).
    - LRU eviction by ``OrderedDict`` (default cap 256).
    - Errors (missing/invalid JSON) return ``None`` and are NOT cached
      (so a fix-and-retry next call still works).
"""

from __future__ import annotations

import json
import threading
from collections import OrderedDict
from pathlib import Path
from typing import Any

_FILE_CACHE_MAX = 256

# key: (str(path), mtime_ns) → value: parsed json (dict | list)
_FILE_CACHE: "OrderedDict[tuple[str, int], Any]" = OrderedDict()
_CACHE_LOCK = threading.Lock()


def read_json_cached(path: Path) -> Any | None:
    """Read + parse a JSON file with mtime-keyed LRU cache.

    Returns parsed JSON on success, ``None`` if the file is missing,
    inaccessible, or contains invalid JSON. Errors are not cached.
    """
    try:
        st = path.stat()
    except OSError:
        return None

    key = (str(path), st.st_mtime_ns)
    with _CACHE_LOCK:
        cached = _FILE_CACHE.get(key)
        if cached is not None:
            _FILE_CACHE.move_to_end(key)
            return cached

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None

    with _CACHE_LOCK:
        _FILE_CACHE[key] = data
        _FILE_CACHE.move_to_end(key)
        while len(_FILE_CACHE) > _FILE_CACHE_MAX:
            _FILE_CACHE.popitem(last=False)
    return data


def clear_cache() -> None:
    """Drop all cached entries. Mainly for tests."""
    with _CACHE_LOCK:
        _FILE_CACHE.clear()
