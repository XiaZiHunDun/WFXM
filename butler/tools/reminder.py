"""Personal reminder tool — set, list, cancel reminders with due-time push.

Supports one-shot and recurring (cron) reminders.
"""

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

from croniter import croniter

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

_CRON_ALIASES: dict[str, str] = {
    "每天": "0 9 * * *",
    "每小时": "0 * * * *",
    "每周一": "0 9 * * 1",
    "每周二": "0 9 * * 2",
    "每周三": "0 9 * * 3",
    "每周四": "0 9 * * 4",
    "每周五": "0 9 * * 5",
    "每周六": "0 9 * * 6",
    "每周日": "0 9 * * 0",
    "工作日": "0 9 * * 1-5",
    "每月1号": "0 9 1 * *",
    "daily": "0 9 * * *",
    "hourly": "0 * * * *",
    "weekdays": "0 9 * * 1-5",
}

_NATURAL_CRON_RE = re.compile(
    r"每天\s*(\d{1,2})[:\s时](\d{1,2})?",
)


def _parse_cron_schedule(text: str) -> str | None:
    """Parse cron expression from user input. Returns 5-field cron or None."""
    stripped = text.strip().lower()

    if stripped in _CRON_ALIASES:
        return _CRON_ALIASES[stripped]

    m = _NATURAL_CRON_RE.search(stripped)
    if m:
        hour = int(m.group(1))
        minute = int(m.group(2) or 0)
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return f"{minute} {hour} * * *"

    parts = stripped.split()
    if len(parts) == 5:
        try:
            croniter(stripped)
            return stripped
        except (ValueError, KeyError):
            pass

    return None


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
        return json.dumps({"ok": False, "error": "when is required (e.g. '30分钟', '14:00', '每天 9:00')"})

    cron_expr = _parse_cron_schedule(raw_when)

    if cron_expr is not None:
        now_cn = datetime.now(_CN_TZ)
        cit = croniter(cron_expr, now_cn)
        next_fire = cit.get_next(datetime)
        rid = uuid.uuid4().hex[:10]
        reminder = {
            "id": rid,
            "message": msg,
            "cron": cron_expr,
            "due_ts": next_fire.timestamp(),
            "due_human": next_fire.strftime("%Y-%m-%d %H:%M"),
            "created_ts": time.time(),
            "status": "pending",
            "recurring": True,
            "fire_count": 0,
        }
        _save_reminder(reminder)
        return json.dumps({
            "ok": True,
            "id": rid,
            "message": msg,
            "recurring": True,
            "cron": cron_expr,
            "next_fire": reminder["due_human"],
        }, ensure_ascii=False)

    due_ts = parse_due_timestamp(raw_when)
    if due_ts is None:
        return json.dumps({
            "ok": False,
            "error": (
                f"Cannot parse time: '{raw_when}'. Examples: "
                "'30分钟', '2小时', '14:00', '2026-05-28 09:00', "
                "'每天 9:00', '工作日', '每小时', '0 9 * * 1-5'"
            ),
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
    """Check for reminders that are past due. Returns fired reminders.

    Recurring reminders auto-reschedule to the next cron fire time.
    """
    now = time.time()
    fired: list[dict[str, Any]] = []
    for reminder in _load_all():
        if reminder.get("status") != "pending":
            continue
        due = reminder.get("due_ts", 0)
        if due <= now:
            snapshot = dict(reminder)
            snapshot["status"] = "fired"
            snapshot["fired_ts"] = now

            if reminder.get("recurring") and reminder.get("cron"):
                now_cn = datetime.now(_CN_TZ)
                try:
                    cit = croniter(reminder["cron"], now_cn)
                    next_fire = cit.get_next(datetime)
                    reminder["due_ts"] = next_fire.timestamp()
                    reminder["due_human"] = next_fire.strftime("%Y-%m-%d %H:%M")
                    reminder["fire_count"] = reminder.get("fire_count", 0) + 1
                    _save_reminder(reminder)
                except (ValueError, KeyError):
                    reminder["status"] = "fired"
                    reminder["fired_ts"] = now
                    _save_reminder(reminder)
            else:
                reminder["status"] = "fired"
                reminder["fired_ts"] = now
                _save_reminder(reminder)

            fired.append(snapshot)
    return fired


def register_reminder_tools(register: Callable[..., None]) -> None:
    register(
        name="set_reminder",
        description=(
            "Set a personal reminder. Supports: relative ('30分钟', '2小时'), "
            "absolute ('14:00', '2026-05-28 09:00'), "
            "recurring cron ('每天 9:00', '工作日', '每小时', '每周一', or 5-field cron '0 9 * * 1-5'). "
            "Recurring reminders auto-reschedule after each fire."
        ),
        schema={
            "type": "object",
            "properties": {
                "message": {"type": "string", "description": "Reminder content"},
                "when": {
                    "type": "string",
                    "description": (
                        "When to remind. Relative: '30分钟'. Absolute: '14:00'. "
                        "Recurring: '每天 9:00', '工作日', '每小时', '每周一', or cron '0 9 * * 1-5'"
                    ),
                },
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
