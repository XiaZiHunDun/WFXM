"""Pending queue for skill create / update (Owner approval)."""

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


def skill_write_approval_enabled() -> bool:
    return env_truthy("BUTLER_SKILL_WRITE_APPROVAL", default=False)


def _pending_path() -> Path:
    d = get_butler_home() / "pending"
    d.mkdir(parents=True, exist_ok=True)
    return d / "skills.json"


def _load_unlocked() -> list[dict[str, Any]]:
    path = _pending_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    items = data.get("items") if isinstance(data, dict) else data
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _save_unlocked(items: list[dict[str, Any]]) -> None:
    _pending_path().write_text(
        json.dumps({"items": items}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def list_skill_pending() -> list[dict[str, Any]]:
    with _LOCK:
        return list(_load_unlocked())


def queue_skill_pending(
    *,
    name: str,
    description: str,
    triggers: list[str],
    content: str,
    source: str = "agent",
) -> dict[str, Any]:
    item = {
        "id": uuid.uuid4().hex[:12],
        "name": name,
        "description": description,
        "triggers": list(triggers),
        "content": content,
        "source": source,
        "ts": time.time(),
    }
    with _LOCK:
        items = _load_unlocked()
        items.append(item)
        _save_unlocked(items)
    return item


def approve_skill_pending(idx: int, skill_manager: Any) -> dict[str, Any]:
    with _LOCK:
        items = _load_unlocked()
        if not (0 <= idx < len(items)):
            return {"ok": False, "error": "index out of range"}
        item = items.pop(idx)
        _save_unlocked(items)
    from butler.skills.write_approval_ops import approve_pending_skill_safe

    return approve_pending_skill_safe(skill_manager, item)


def approve_all_skill_pending(skill_manager: Any) -> int:
    count = 0
    while True:
        with _LOCK:
            items = _load_unlocked()
            if not items:
                break
            item = items.pop(0)
            _save_unlocked(items)
        from butler.skills.write_approval_ops import create_pending_skill_safe

        if create_pending_skill_safe(skill_manager, item):
            count += 1
    return count


def reject_skill_pending(idx: int) -> bool:
    with _LOCK:
        items = _load_unlocked()
        if not (0 <= idx < len(items)):
            return False
        items.pop(idx)
        _save_unlocked(items)
        return True


def reject_all_skill_pending() -> int:
    with _LOCK:
        n = len(_load_unlocked())
        _save_unlocked([])
        return n


def format_skill_pending_lines(limit: int = 15) -> list[str]:
    pending = list_skill_pending()
    if not pending:
        return []
    lines = [f"技能待审: {len(pending)} 条", ""]
    for i, item in enumerate(pending[:limit], start=1):
        name = item.get("name") or "?"
        desc = str(item.get("description") or "").strip()[:80]
        lines.append(f"{i}. {name} — {desc}")
    if len(pending) > limit:
        lines.append(f"… 另有 {len(pending) - limit} 条")
    lines.append("")
    lines.append("批准: /批准技能 <序号>  拒绝: /拒绝技能 <序号>")
    return lines


__all__ = [
    "approve_all_skill_pending",
    "approve_skill_pending",
    "format_skill_pending_lines",
    "list_skill_pending",
    "queue_skill_pending",
    "reject_all_skill_pending",
    "reject_skill_pending",
    "skill_write_approval_enabled",
]
