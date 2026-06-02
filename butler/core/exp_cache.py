"""Lightweight LLM response cache by prompt fingerprint (PR-X5 / MetaGPT subset)."""

from __future__ import annotations

import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Any

from butler.core.meta_flags import exp_cache_enabled
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_MAX_ENTRIES = 500

# Sprint 11 PERF-11-2/3: per-path in-memory cache，lookup O(1)，避免
# 每次 LLM 调用都全文件 read + 逐行 json.loads。store 仍写全文件
# （保持持久化语义，避免崩溃丢数据），但 store 频率远低于 lookup。
_MEM_CACHE: dict[str, dict[str, dict[str, Any]]] = {}
_MEM_LOADED: dict[str, bool] = {}


def _cache_enabled() -> bool:
    return exp_cache_enabled()


def _max_entries() -> int:
    import os

    try:
        return max(10, min(5000, int(os.getenv("BUTLER_EXP_CACHE_MAX", "500"))))
    except ValueError:
        return _MAX_ENTRIES


def _resolve_cache_path() -> Path | None:
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        pm = getattr(orch, "project_manager", None) if orch else None
        if pm is not None:
            from butler.execution_context import get_current_session_key

            proj = pm.get_current(session_key=str(get_current_session_key() or ""))
            if proj is not None:
                return Path(proj.workspace).expanduser().resolve() / ".butler" / "experiences" / "llm_cache.jsonl"
    except Exception as exc:
        logger.debug("resolve cache path skipped: %s", exc)
    home = Path.home() / ".butler" / "experiences" / "llm_cache.jsonl"
    return home


def fingerprint_llm_request(
    *,
    provider: str,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict] | None = None,
) -> str:
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


def _read_entries(path: Path) -> dict[str, dict[str, Any]]:
    """Return in-memory cache for path（lazy load once per path）。

    Sprint 11 PERF-11-2: 修复前每次 read 全文件 + 逐行 json.loads。
    修复后：path 首次访问时 load 一次，之后只读 in-memory dict。
    """
    cache_key = str(path)
    if _MEM_LOADED.get(cache_key):
        return _MEM_CACHE.setdefault(cache_key, {})
    out: dict[str, dict[str, Any]] = {}
    if path.is_file():
        try:
            for line in path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                if isinstance(row, dict) and row.get("fp"):
                    out[str(row["fp"])] = row
        except (OSError, json.JSONDecodeError) as exc:
            logger.debug("exp_cache read %s: %s", path, exc)
    _MEM_CACHE[cache_key] = out
    _MEM_LOADED[cache_key] = True
    return out


def _write_entries(path: Path, entries: dict[str, dict[str, Any]]) -> None:
    """Write entries to disk AND update in-memory cache.

    Sprint 11 PERF-11-3: 写全文件（保持原持久化语义），但同时
    同步 in-memory dict，避免后续 lookup 重读。
    """
    cache_key = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    items = list(entries.values())[-_max_entries():]
    text = "\n".join(json.dumps(it, ensure_ascii=False) for it in items) + ("\n" if items else "")
    try:
        from butler.io.atomic_write import atomic_write_text

        atomic_write_text(path, text)
    except Exception:
        path.write_text(text, encoding="utf-8")
    # Sprint 11 PERF-11-2: 同步 in-memory cache（截断到 max_entries）
    _MEM_CACHE[cache_key] = {str(it.get("fp")): it for it in items if it.get("fp")}
    _MEM_LOADED[cache_key] = True


def lookup_cached_response(fp: str) -> str | None:
    if not _cache_enabled() or not fp:
        return None
    path = _resolve_cache_path()
    if path is None:
        return None
    with _lock:
        hit = _read_entries(path).get(fp)
    if not hit:
        return None
    content = str(hit.get("content") or "").strip()
    return content or None


def store_cached_response(
    fp: str,
    content: str,
    *,
    provider: str = "",
    model: str = "",
) -> None:
    if not _cache_enabled() or not fp or not str(content or "").strip():
        return
    if not env_truthy("BUTLER_EXP_CACHE_STORE", default=True):
        return
    path = _resolve_cache_path()
    if path is None:
        return
    row = {
        "fp": fp,
        "content": str(content)[:16000],
        "provider": provider,
        "model": model,
    }
    with _lock:
        entries = _read_entries(path)
        entries[fp] = row
        if len(entries) > _max_entries():
            for key in list(entries.keys())[: len(entries) - _max_entries()]:
                entries.pop(key, None)
        _write_entries(path, entries)


__all__ = [
    "fingerprint_llm_request",
    "lookup_cached_response",
    "store_cached_response",
]
