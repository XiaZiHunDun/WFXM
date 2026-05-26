"""Personal reminder tool — set, list, cancel reminders with due-time push."""

from __future__ import annotations

import json
import logging
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

_CN_TZ = timezone(timedelta(hours=8))
_TIME_PATTERN = re.compile(
    r"(\d+)\s*(秒|分钟|分|小时|时|天|日|s|sec|min|minute|minutes|h|hour|hours|d|day|days)",
    re.IGNORECASE,
)
_UNIT_MAP: dict[str, int] = {
    "秒": 1, "s": 1, "sec": 1,
    "分钟": 60, "分": 60, "min": 60, "minute": 60, "minutes": 60,
    "小时": 3600, "时": 3600, "h": 3600, "hour": 3600, "hours": 3600,
    "天": 86400, "日": 86400, "d": 86400, "day": 86400, "days": 86400,
}


def _reminders_dir() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "reminders"


def _parse_relative_time(text: str) -> int | None:
    """Parse '30分钟', '2小时', '1天' etc. Returns seconds or None."""
    m = _TIME_PATTERN.search(text)
    if not m:
        return None
    val = int(m.group(1))
    unit = m.group(2).lower()
    multiplier = _UNIT_MAP.get(unit)
    if multiplier is None:
        return None
    return val * multiplier


def _parse_absolute_time(text: str) -> float | None:
    """Parse HH:MM or YYYY-MM-DD HH:MM format."""
    for fmt in ("%Y-%m-%d %H:%M", "%H:%M", "%Y/%m/%d %H:%M"):
        try:
            dt = datetime.strptime(text.strip(), fmt)
            if dt.year == 1900:
                now = datetime.now(_CN_TZ)
                dt = dt.replace(year=now.year, month=now.month, day=now.day, tzinfo=_CN_TZ)
                if dt < now:
                    dt += timedelta(days=1)
            else:
                dt = dt.replace(tzinfo=_CN_TZ)
            return dt.timestamp()
        except ValueError:
            continue
    return None


def parse_due_timestamp(when: str) -> float | None:
    """Convert user-facing time spec to a UTC timestamp."""
    secs = _parse_relative_time(when)
    if secs is not None:
        return time.time() + secs
    return _parse_absolute_time(when)


def _save_reminder(reminder: dict[str, Any]) -> Path:
    root = _reminders_dir()
    root.mkdir(parents=True, exist_ok=True)
    rid = reminder["id"]
    path = root / f"{rid}.json"
    path.write_text(json.dumps(reminder, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _load_all() -> list[dict[str, Any]]:
    root = _reminders_dir()
    if not root.is_dir():
        return []
    items = []
    for p in sorted(root.glob("*.json")):
        try:
            items.append(json.loads(p.read_text(encoding="utf-8")))
        except (json.JSONDecodeError, OSError):
            continue
    return items


def _delete_reminder(rid: str) -> bool:
    root = _reminders_dir()
    path = root / f"{rid}.json"
    if path.is_file():
        path.unlink()
        return True
    return False


def tool_set_reminder(message: str, when: str, **_: Any) -> str:
    msg = (message or "").strip()
    raw_when = (when or "").strip()
    if not msg:
        return json.dumps({"ok": False, "error": "message is required"})
    if not raw_when:
        return json.dumps({"ok": False, "error": "when is required (e.g. '30分钟', '14:00')"})

    due_ts = parse_due_timestamp(raw_when)
    if due_ts is None:
        return json.dumps({
            "ok": False,
            "error": f"Cannot parse time: '{raw_when}'. Examples: '30分钟', '2小时', '14:00', '2026-05-28 09:00'",
        })

    rid = uuid.uuid4().hex[:10]
    reminder = {
        "id": rid,
        "message": msg,
        "due_ts": due_ts,
        "due_human": datetime.fromtimestamp(due_ts, tz=_CN_TZ).strftime("%Y-%m-%d %H:%M"),
        "created_ts": time.time(),
        "status": "pending",
    }
    _save_reminder(reminder)
    return json.dumps({
        "ok": True,
        "id": rid,
        "message": msg,
        "due": reminder["due_human"],
    }, ensure_ascii=False)


def tool_list_reminders(**_: Any) -> str:
    items = _load_all()
    pending = [r for r in items if r.get("status") == "pending"]
    fired = [r for r in items if r.get("status") == "fired"]
    return json.dumps({
        "ok": True,
        "pending": len(pending),
        "fired": len(fired),
        "reminders": pending[:20],
    }, ensure_ascii=False)


def tool_cancel_reminder(reminder_id: str, **_: Any) -> str:
    rid = (reminder_id or "").strip()
    if not rid:
        return json.dumps({"ok": False, "error": "reminder_id is required"})
    if _delete_reminder(rid):
        return json.dumps({"ok": True, "cancelled": rid})
    return json.dumps({"ok": False, "error": f"Reminder '{rid}' not found"})


def poll_due_reminders() -> list[dict[str, Any]]:
    """Check for reminders that are past due. Returns fired reminders."""
    now = time.time()
    fired: list[dict[str, Any]] = []
    for reminder in _load_all():
        if reminder.get("status") != "pending":
            continue
        due = reminder.get("due_ts", 0)
        if due <= now:
            reminder["status"] = "fired"
            reminder["fired_ts"] = now
            _save_reminder(reminder)
            fired.append(reminder)
    return fired


def register_reminder_tools(register: Callable[..., None]) -> None:
    register(
        name="set_reminder",
        description=(
            "Set a personal reminder. Time supports relative ('30分钟', '2小时', '1天') "
            "or absolute ('14:00', '2026-05-28 09:00'). Reminder will be pushed via WeChat."
        ),
        schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Reminder content"},
                "when": {"type": "string", "description": "When to remind (e.g. '30分钟', '14:00')"},
            },
            "required": ["message", "when"],
        },
        handler=tool_set_reminder,
        toolset="reminder",
    )
    register(
        name="list_reminders",
        description="List pending and recently fired reminders.",
        schema={"type": "object", "properties": {}},
        handler=tool_list_reminders,
        toolset="reminder",
    )
    register(
        name="cancel_reminder",
        description="Cancel a pending reminder by id.",
        schema={
            "type": "object",
            "properties": {
                "reminder_id": {"type": "string", "description": "Reminder id to cancel"},
            },
            "required": ["reminder_id"],
        },
        handler=tool_cancel_reminder,
        toolset="reminder",
    )
