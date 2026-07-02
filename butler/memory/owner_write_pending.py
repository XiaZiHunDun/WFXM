"""Pending queue for owner_profile / owner_experience butler_remember writes."""

from __future__ import annotations

import json
import os
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from butler.config import get_butler_home
from butler.env_parse import env_truthy

_LOCK = threading.RLock()


def memory_write_approval_mode() -> str:
    """``owner_scopes`` (default) | ``all`` | ``0`` (disabled)."""
    raw = os.getenv("BUTLER_MEMORY_WRITE_APPROVAL", "owner_scopes").strip().lower()
    if raw in ("0", "off", "false", "none", "disabled"):
        return "0"
    if raw == "all":
        return "all"
    return "owner_scopes"


def memory_write_approval_enabled() -> bool:
    return memory_write_approval_mode() != "0"


def scope_requires_write_approval(scope: str, action: str = "append") -> bool:
    mode = memory_write_approval_mode()
    if mode == "0":
        return False
    scope = str(scope or "").strip()
    action = str(action or "append").strip().lower()
    if mode == "owner_scopes":
        return scope in ("owner_profile", "owner_experience")
    if mode == "all":
        if scope == "project_notes" and action == "append":
            return False
        return scope in ("owner_profile", "owner_experience", "project_notes")
    return False


def _pending_path() -> Path:
    d = get_butler_home() / "pending"
    d.mkdir(parents=True, exist_ok=True)
    return d / "owner_memory.json"


def _load_unlocked() -> list[dict[str, Any]]:
    path = _pending_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    return [i for i in items if isinstance(i, dict)]


def _save_unlocked(items: list[dict[str, Any]]) -> None:
    path = _pending_path()
    path.write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_owner_pending() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_load_unlocked())


def queue_owner_write(
    *,
    scope: str,
    content: str,
    action: str = "append",
    old_content: str = "",
    category: str = "",
    section: str = "",
) -> dict[str, Any]:
    item = {
        "id": uuid.uuid4().hex[:12],
        "scope": scope,
        "action": action,
        "content": content,
        "old_content": old_content,
        "category": category,
        "section": section,
        "ts": time.time(),
    }
    with _LOCK:
        items = _load_unlocked()
        items.append(item)
        _save_unlocked(items)
    return item


def approve_owner_pending(idx: int, butler_global: Any) -> dict[str, Any]:
    with _LOCK:
        items = _load_unlocked()
        if not (0 <= idx < len(items)):
            return {"ok": False, "error": "index out of range"}
        item = items.pop(idx)
        _save_unlocked(items)
    return _apply_owner_item(butler_global, item)


def approve_all_owner_pending(butler_global: Any) -> int:
    count = 0
    while True:
        with _LOCK:
            items = _load_unlocked()
            if not items:
                break
            item = items.pop(0)
            _save_unlocked(items)
        result = _apply_owner_item(butler_global, item)
        if result.get("ok"):
            count += 1
    return count


def reject_owner_pending(idx: int) -> bool:
    with _LOCK:
        items = _load_unlocked()
        if not (0 <= idx < len(items)):
            return False
        items.pop(idx)
        _save_unlocked(items)
        return True


def reject_all_owner_pending() -> int:
    with _LOCK:
        n = len(_load_unlocked())
        _save_unlocked([])
        return n


def _apply_owner_item(butler_global: Any, item: dict[str, Any]) -> dict[str, Any]:
    from butler.memory.facade import ButlerMemoryService

    provider = ButlerMemoryService()
    provider._butler_global = butler_global  # noqa: SLF001 — approval apply path
    args: dict[str, Any] = {
        "scope": item.get("scope"),
        "content": item.get("content"),
        "action": item.get("action") or "append",
    }
    if item.get("old_content"):
        args["old_content"] = item["old_content"]
    if item.get("category"):
        args["category"] = item["category"]
    if item.get("section"):
        args["section"] = item["section"]
    raw = provider._remember_direct(args)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = {"ok": False, "error": raw}
    return payload


def format_owner_pending_lines(limit: int = 20) -> list[str]:
    pending = list_owner_pending()
    if not pending:
        return []
    lines = [f"所有者记忆待审: {len(pending)} 条", ""]
    for i, item in enumerate(pending[:limit], start=1):
        scope = item.get("scope") or "?"
        action = item.get("action") or "append"
        body = str(item.get("content") or "").strip()
        if len(body) > 100:
            body = body[:97] + "..."
        lines.append(f"{i}. [{scope}/{action}] {body}")
    if len(pending) > limit:
        lines.append(f"… 另有 {len(pending) - limit} 条")
    return lines


__all__ = [
    "approve_all_owner_pending",
    "approve_owner_pending",
    "format_owner_pending_lines",
    "list_owner_pending",
    "memory_write_approval_enabled",
    "memory_write_approval_mode",
    "queue_owner_write",
    "reject_all_owner_pending",
    "reject_owner_pending",
    "scope_requires_write_approval",
]
