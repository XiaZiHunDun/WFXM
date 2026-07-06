"""Session-scoped short TTL cache for read-only tool results (Langflow subset)."""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any

from butler.env_parse import env_truthy, float_env

_CACHEABLE = frozenset({
    "read_file",
    "search_files",
    "list_directory",
    "butler_recall",
    "search_transcript",
    "skills_list",
    "skill_view",
})

_STORE_LOCK = threading.RLock()
_STORE: dict[str, OrderedDict[str, "_CacheEntry"]] = {}
_MAX_PER_SCOPE = 200


@dataclass
class _CacheEntry:
    result: str
    expires_at: float


def tool_result_cache_enabled() -> bool:
    return bool(env_truthy("BUTLER_TOOL_RESULT_CACHE", default=True))


def tool_result_cache_ttl_seconds() -> float:
    try:
        return float(float_env("BUTLER_TOOL_RESULT_CACHE_TTL", 120, min=5.0))
    except ValueError:
        return 120.0


def _session_bucket(session_key: str) -> str:
    return str(session_key or "default").strip() or "default"


def cache_key(tool_name: str, args: dict[str, Any]) -> str:
    payload = json.dumps(
        {"tool": tool_name, "args": args},
        sort_keys=True,
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def is_cacheable_tool(name: str) -> bool:
    return str(name or "").strip() in _CACHEABLE


def get_cached_result(
    tool_name: str,
    args: dict[str, Any],
    *,
    session_key: str = "",
) -> str | None:
    if not tool_result_cache_enabled() or not is_cacheable_tool(tool_name):
        return None
    sk = _session_bucket(session_key)
    key = cache_key(tool_name, args)
    now = time.time()
    with _STORE_LOCK:
        bucket = _STORE.get(sk)
        if bucket is None:
            return None
        entry = bucket.get(key)
        if entry is None:
            return None
        if now > entry.expires_at:
            bucket.pop(key, None)
            return None
        bucket.move_to_end(key)
        return entry.result


def set_cached_result(
    tool_name: str,
    args: dict[str, Any],
    result: str,
    *,
    session_key: str = "",
) -> None:
    if not tool_result_cache_enabled() or not is_cacheable_tool(tool_name):
        return
    if not (result or "").strip():
        return
    sk = _session_bucket(session_key)
    key = cache_key(tool_name, args)
    with _STORE_LOCK:
        bucket = _STORE.setdefault(sk, OrderedDict())
        bucket[key] = _CacheEntry(
            result=result,
            expires_at=time.time() + tool_result_cache_ttl_seconds(),
        )
        bucket.move_to_end(key)
        while len(bucket) > _MAX_PER_SCOPE:
            bucket.popitem(last=False)


def clear_session_tool_cache(session_key: str = "") -> None:
    with _STORE_LOCK:
        _STORE.pop(_session_bucket(session_key), None)
