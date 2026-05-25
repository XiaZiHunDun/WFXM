"""Session-scoped short TTL cache for read-only tool results (Langflow subset)."""

from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from typing import Any

from butler.env_parse import env_truthy

_CACHEABLE = frozenset({
    "read_file",
    "search_files",
    "list_directory",
    "butler_recall",
    "search_transcript",
    "skills_list",
    "skill_view",
})

_STORE: dict[str, dict[str, _CacheEntry]] = {}


@dataclass
class _CacheEntry:
    result: str
    expires_at: float


def tool_result_cache_enabled() -> bool:
    return env_truthy("BUTLER_TOOL_RESULT_CACHE", default=True)


def tool_result_cache_ttl_seconds() -> float:
    try:
        return max(5.0, float(os.getenv("BUTLER_TOOL_RESULT_CACHE_TTL", "120")))
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
    bucket = _STORE.get(_session_bucket(session_key), {})
    entry = bucket.get(cache_key(tool_name, args))
    if entry is None:
        return None
    if time.time() > entry.expires_at:
        bucket.pop(cache_key(tool_name, args), None)
        return None
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
    bucket = _STORE.setdefault(sk, {})
    if len(bucket) > 200:
        oldest = sorted(bucket.items(), key=lambda kv: kv[1].expires_at)[:50]
        for k, _ in oldest:
            bucket.pop(k, None)
    bucket[cache_key(tool_name, args)] = _CacheEntry(
        result=result,
        expires_at=time.time() + tool_result_cache_ttl_seconds(),
    )


def clear_session_tool_cache(session_key: str = "") -> None:
    _STORE.pop(_session_bucket(session_key), None)
