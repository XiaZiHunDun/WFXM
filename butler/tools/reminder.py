"""Personal reminder tool — set, list, cancel reminders with due-time push.

Supports one-shot and recurring (cron) reminders.
"""

from __future__ import annotations

import json
import logging
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast

from croniter import croniter  # type: ignore[import-untyped]

from butler.tools.pim_schema import REMINDER_STATUSES
from butler.tools.tenant_store import TenantStore

logger = logging.getLogger(__name__)

_reminder_store = TenantStore("reminders")

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
    "每月5号": "0 9 5 * *",
    "每月10号": "0 9 10 * *",
    "每月15号": "0 9 15 * *",
    "每月20号": "0 9 20 * *",
    "每月25号": "0 9 25 * *",
    "每月底": "0 9 L * *",
    "daily": "0 9 * * *",
    "hourly": "0 * * * *",
    "weekdays": "0 9 * * 1-5",
}

_NATURAL_CRON_RE = re.compile(
    r"每天\s*(\d{1,2})[:\s时](\d{1,2})?",
)
_MONTHLY_RE = re.compile(r"每月(\d{1,2})号")

_RELATIVE_DATE_PATTERNS: dict[str, int] = {
    "今天": 0, "明天": 1, "后天": 2, "大后天": 3,
}

_WEEKDAY_NAMES: dict[str, int] = {
    "周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6,
    "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4, "星期六": 5, "星期日": 6, "星期天": 6,
}

_TIME_OF_DAY: dict[str, int] = {
    "早上": 8, "上午": 9, "中午": 12, "下午": 14, "傍晚": 17, "晚上": 20,
}

_NATURAL_DATETIME_RE = re.compile(
    r"^(?P<date>"
    r"今天|明天|后天|大后天|"
    r"这?周[一二三四五六日]|"
    r"下周[一二三四五六日]|"
    r"下?[个]?星期[一二三四五六日天]"
    r")"
    r"\s*"
    r"(?P<period>早上|上午|中午|下午|傍晚|晚上)?"
    r"\s*"
    r"(?:(?P<hour>\d{1,2})[点时:]?)?"
    r"(?:(?P<minute>\d{1,2})[分]?)?"
    r"\s*"
    r"(?P<half>半)?$"
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

    m = _MONTHLY_RE.search(stripped)
    if m:
        day = int(m.group(1))
        if 1 <= day <= 31:
            return f"0 9 {day} * *"

    parts = stripped.split()
    if len(parts) == 5:
        try:
            croniter(stripped)
            return stripped
        except (ValueError, KeyError):
            pass

    return None


def _reminders_dir() -> Path:
    return Path(_reminder_store.storage_dir())


def migrate_legacy_reminders(butler_home: Path) -> None:
    """Move pre-tenant ``{butler_home}/reminders`` into ``tenants/default/reminders``."""
    from butler.tenant import DEFAULT_TENANT, tenant_root

    legacy = Path(butler_home).expanduser().resolve() / "reminders"
    target = tenant_root(butler_home, DEFAULT_TENANT) / "reminders"
    if legacy.is_dir() and not target.exists():
        import shutil

        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(legacy), str(target))
        logger.info("Migrated reminders to %s", target)


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


def _weekday_from_date_token(date_str: str) -> tuple[int, bool] | None:
    """Return (weekday 0=Mon, is_next_week) or None."""
    if date_str in _RELATIVE_DATE_PATTERNS:
        return None

    is_next_week = date_str.startswith("下")
    remainder = date_str
    if date_str.startswith("这"):
        remainder = date_str[1:]
    elif is_next_week:
        remainder = date_str[1:]
        if remainder.startswith("个"):
            remainder = remainder[1:]

    if remainder.startswith("星期"):
        name = remainder[2:]
    elif remainder.startswith("周"):
        name = remainder[1:]
    else:
        return None

    if name == "日":
        name = "天"
    weekday = _WEEKDAY_NAMES.get(name if len(name) > 1 else f"周{name}")
    if weekday is None and name in ("一", "二", "三", "四", "五", "六", "日", "天"):
        weekday = _WEEKDAY_NAMES.get(f"周{'日' if name == '天' else name}")
    if weekday is None:
        return None
    return weekday, is_next_week


def _resolve_natural_time(
    period: str | None,
    hour_str: str | None,
    minute_str: str | None,
    half: str | None,
) -> tuple[int, int] | None:
    hour = 9
    minute = 0

    if hour_str:
        hour = int(hour_str)
        if not (0 <= hour <= 23):
            return None
    elif period:
        hour = _TIME_OF_DAY.get(period, 9)

    if half:
        minute = 30
    elif minute_str:
        minute = int(minute_str)
        if not (0 <= minute <= 59):
            return None

    if period in ("下午", "晚上", "傍晚") and hour_str:
        h = int(hour_str)
        if 1 <= h <= 11:
            hour = h + 12
        elif h == 12 and period == "下午":
            hour = 12

    if not (0 <= hour <= 23):
        return None
    return hour, minute


def _parse_natural_datetime(text: str) -> float | None:
    """Parse Chinese natural date/time like '明天早上9点', '下周一'."""
    stripped = text.strip()
    m = _NATURAL_DATETIME_RE.match(stripped)
    if not m:
        return None

    now = datetime.now(_CN_TZ)
    date_str = m.group("date")

    if date_str in _RELATIVE_DATE_PATTERNS:
        target_date = (now + timedelta(days=_RELATIVE_DATE_PATTERNS[date_str])).date()
    else:
        wd_info = _weekday_from_date_token(date_str)
        if wd_info is None:
            return None
        target_wd, is_next_week = wd_info
        current_wd = now.weekday()
        if is_next_week:
            days_to_next_monday = (7 - current_wd) % 7
            if days_to_next_monday == 0:
                days_to_next_monday = 7
            days = days_to_next_monday + target_wd
        else:
            days = (target_wd - current_wd) % 7
        target_date = (now + timedelta(days=days)).date()

    time_parts = _resolve_natural_time(
        m.group("period"),
        m.group("hour"),
        m.group("minute"),
        m.group("half"),
    )
    if time_parts is None:
        return None
    hour, minute = time_parts

    dt = datetime(
        target_date.year, target_date.month, target_date.day,
        hour, minute, tzinfo=_CN_TZ,
    )
    if dt <= now:
        dt += timedelta(days=1)
    return dt.timestamp()


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
    natural = _parse_natural_datetime(when)
    if natural is not None:
        return natural
    return _parse_absolute_time(when)


def _save_reminder(reminder: dict[str, Any]) -> Path:
    return Path(_reminder_store.save(reminder))


def _load_all() -> list[dict[str, Any]]:
    return list(_reminder_store.load_all())


def _delete_reminder(rid: str) -> bool:
    return bool(_reminder_store.delete(rid))


def tool_set_reminder(message: str, when: str, **_: Any) -> str:
    from butler.tools.pim_schema import MAX_ACTIVE_REMINDERS, MAX_REMINDER_MESSAGE_LEN

    msg = (message or "").strip()[:MAX_REMINDER_MESSAGE_LEN]
    raw_when = (when or "").strip()
    if not msg:
        return json.dumps({"ok": False, "error": "message is required"})
    if not raw_when:
        return json.dumps({"ok": False, "error": "when is required (e.g. '30分钟', '14:00', '每天 9:00')"})

    active_count = sum(1 for r in _load_all() if r.get("status") == "pending")
    if active_count >= MAX_ACTIVE_REMINDERS:
        return json.dumps({
            "ok": False,
            "error": f"活跃提醒已达上限 ({MAX_ACTIVE_REMINDERS})，请先取消不需要的提醒",
        })

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


def tool_reminder_list_active(**_: Any) -> str:
    """Return only active (pending) reminders, sorted by due_ts."""
    items = _load_all()
    active = sorted(
        (r for r in items if r.get("status") == "pending"),
        key=lambda r: r.get("due_ts", 0),
    )
    return json.dumps({
        "ok": True,
        "count": len(active),
        "reminders": active[:30],
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
        description=(
            "【audit·全状态 dump】导出 reminders 表全部行：fired / cancelled / pending 均含。"
            "场景：复盘「以前设过什么」「上次响了吗」。"
            "非日程预览； upcoming 队列用 reminder_list_active。"
        ),
        schema={"type": "object", "properties": {}},
        handler=tool_list_reminders,
        toolset="reminder",
    )
    register(
        name="reminder_list_active",
        description=(
            "【schedule·upcoming queue】filter status=pending，按 trigger_at 排序的下一次闹钟。"
            "场景：「接下来要响什么」「最近几个闹钟」。"
            "无 fired/cancelled 归档；全量审计用 list_reminders。"
        ),
        schema={"type": "object", "properties": {}},
        handler=tool_reminder_list_active,
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
