"""Personal habit tracker — daily check-in with streaks and stats.

Habits are tenant-scoped, stored under
``~/.butler/tenants/<tenant>/habits/``:
  - ``<id>.json``    — habit definition
  - ``checkins/``    — ``<habit_id>_<YYYY-MM-DD>.json`` per check-in

Core value is streak counting and completion rates, not raw data storage.
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, cast

from butler.tools._file_cache import read_json_cached
from butler.tools.pim_schema import (
    HABIT_FREQUENCIES as _VALID_FREQUENCIES,
    HABIT_FREQ_LABELS as _FREQ_LABELS,
    MAX_ACTIVE_HABITS as _MAX_HABITS,
)
from butler.tools.tenant_store import TenantStore

logger = logging.getLogger(__name__)

_CN_TZ = timezone(timedelta(hours=8))

_store = TenantStore("habits", env_toggle="BUTLER_HABITS_ENABLED")
_checkin_store = TenantStore("habits/checkins", env_toggle="BUTLER_HABITS_ENABLED")


def _habits_enabled() -> bool:
    return bool(_store.enabled())


def _habits_dir() -> Path:
    return Path(_store.storage_dir())


def _checkins_dir() -> Path:
    d = Path(_checkin_store.storage_dir())
    d.mkdir(parents=True, exist_ok=True)
    return d


def _today_str() -> str:
    return datetime.now(_CN_TZ).strftime("%Y-%m-%d")


def _save_checkin(habit_id: str, date: str, count: int = 1, note: str = "") -> Path:
    data: dict[str, Any] = {
        "id": f"{habit_id}_{date}",
        "habit_id": habit_id,
        "date": date,
        "count": count,
        "note": note,
        "created_at": time.time(),
    }
    return Path(_checkin_store.save(data))


def _load_checkins(habit_id: str, days: int = 30) -> list[dict[str, Any]]:
    cd = _checkins_dir()
    if not cd.is_dir():
        return []
    result: list[dict[str, Any]] = []
    for f in sorted(cd.glob(f"{habit_id}_*.json"), reverse=True):
        data = read_json_cached(f)
        if isinstance(data, dict):
            result.append(data)
        if len(result) >= days:
            break
    return result


def _get_checkin(habit_id: str, date: str) -> dict[str, Any] | None:
    path = _checkins_dir() / f"{habit_id}_{date}.json"
    if not path.is_file():
        return None
    data = read_json_cached(path)
    return data if isinstance(data, dict) else None


def _calc_streak(habit_id: str) -> int:
    """Calculate current consecutive-day streak (including today)."""
    today = datetime.now(_CN_TZ).date()
    streak = 0
    for i in range(365):
        d = (today - timedelta(days=i)).isoformat()
        if _get_checkin(habit_id, d):
            streak += 1
        else:
            if i == 0:
                continue
            break
    return streak


def _calc_weekly_count(habit_id: str) -> int:
    """Count check-ins in the current week (Mon-Sun)."""
    today = datetime.now(_CN_TZ).date()
    week_start = today - timedelta(days=today.weekday())
    count = 0
    for i in range(7):
        d = (week_start + timedelta(days=i)).isoformat()
        ci = _get_checkin(habit_id, d)
        if ci:
            count += ci.get("count", 1)
    return count


def _calc_completion_rate(habit_id: str, days: int = 30) -> float:
    today = datetime.now(_CN_TZ).date()
    checked = 0
    for i in range(days):
        d = (today - timedelta(days=i)).isoformat()
        if _get_checkin(habit_id, d):
            checked += 1
    return round(checked / max(days, 1) * 100, 1)


def _find_habit_by_prefix_or_name(identifier: str) -> dict[str, Any] | None:
    hid = identifier.strip()
    if not hid:
        return None
    habit = _store.load_one(hid)
    if habit:
        return cast(dict[str, Any], habit)
    for h in _store.load_all():
        if h["id"].startswith(hid) or h.get("name", "").lower() == hid.lower():
            return cast(dict[str, Any], h)
    return None


# ── Tool Handlers ──────────────────────────────────────────────


def tool_habit_create(
    name: str,
    frequency: str = "daily",
    target_count: int = 1,
    **_: Any,
) -> str:
    if not _habits_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_HABITS_ENABLED=0"})

    name = (name or "").strip()[:100]
    if not name:
        return json.dumps({"ok": False, "error": "name is required"})

    all_habits = _store.load_all()
    active = [h for h in all_habits if h.get("active", True)]
    if len(active) >= _MAX_HABITS:
        return json.dumps({
            "ok": False,
            "error": f"Active habit limit reached ({_MAX_HABITS}). Archive some first.",
        })

    for h in all_habits:
        if h.get("name", "").lower() == name.lower() and h.get("active", True):
            return json.dumps({
                "ok": False,
                "error": f"Habit '{name}' already exists [{h['id'][:4]}]",
            })

    freq = frequency.strip().lower()
    if freq not in _VALID_FREQUENCIES:
        freq = "daily"

    hid = uuid.uuid4().hex[:10]
    habit: dict[str, Any] = {
        "id": hid,
        "name": name,
        "frequency": freq,
        "target_count": max(1, int(target_count or 1)),
        "active": True,
        "created_at": time.time(),
    }
    _store.save(habit)

    return json.dumps({
        "ok": True,
        "habit_id": hid,
        "name": name,
        "frequency": freq,
        "target_count": habit["target_count"],
    }, ensure_ascii=False)


def tool_habit_checkin(
    habit_id: str,
    count: int = 1,
    note: str = "",
    date: str = "",
    **_: Any,
) -> str:
    if not _habits_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_HABITS_ENABLED=0"})

    habit = _find_habit_by_prefix_or_name(habit_id or "")
    if habit is None:
        return json.dumps({"ok": False, "error": f"Habit '{habit_id}' not found"})

    hid = habit["id"]
    checkin_date = date.strip() if date else _today_str()
    try:
        datetime.strptime(checkin_date[:10], "%Y-%m-%d")
        checkin_date = checkin_date[:10]
    except ValueError:
        checkin_date = _today_str()

    existing = _get_checkin(hid, checkin_date)
    cnt = max(1, int(count or 1))

    clean_note = (note or "").strip()[:500]

    if existing:
        existing["count"] = existing.get("count", 0) + cnt
        if clean_note:
            existing["note"] = ((existing.get("note") or "") + "; " + clean_note).strip("; ")[:1000]
        path = _checkins_dir() / f"{hid}_{checkin_date}.json"
        path.write_text(json.dumps(existing, ensure_ascii=False, indent=2), encoding="utf-8")
        total_count = existing["count"]
    else:
        _save_checkin(hid, checkin_date, cnt, clean_note)
        total_count = cnt

    streak = _calc_streak(hid)

    return json.dumps({
        "ok": True,
        "habit": habit["name"],
        "date": checkin_date,
        "count": total_count,
        "streak": streak,
    }, ensure_ascii=False)


def tool_habit_stats(
    habit_id: str = "",
    **_: Any,
) -> str:
    if not _habits_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_HABITS_ENABLED=0"})

    if habit_id:
        habit = _find_habit_by_prefix_or_name(habit_id)
        if habit is None:
            return json.dumps({"ok": False, "error": f"Habit '{habit_id}' not found"})
        return _single_habit_stats(habit)

    all_habits = [h for h in _store.load_all() if h.get("active", True)]
    if not all_habits:
        return json.dumps({"ok": True, "habits": [], "message": "No active habits"})

    stats_list = []
    for h in all_habits:
        hid = h["id"]
        streak = _calc_streak(hid)
        rate_30 = _calc_completion_rate(hid, 30)
        today_done = _get_checkin(hid, _today_str()) is not None
        weekly = _calc_weekly_count(hid) if h.get("frequency") == "weekly" else None

        entry: dict[str, Any] = {
            "habit_id": hid,
            "name": h["name"],
            "frequency": h.get("frequency", "daily"),
            "streak": streak,
            "rate_30d": rate_30,
            "today_done": today_done,
        }
        if weekly is not None:
            entry["weekly_count"] = weekly
            entry["weekly_target"] = h.get("target_count", 1)
        stats_list.append(entry)

    return json.dumps({"ok": True, "habits": stats_list}, ensure_ascii=False)


def _single_habit_stats(habit: dict[str, Any]) -> str:
    hid = habit["id"]
    streak = _calc_streak(hid)
    rate_7 = _calc_completion_rate(hid, 7)
    rate_30 = _calc_completion_rate(hid, 30)
    today_done = _get_checkin(hid, _today_str()) is not None
    recent = _load_checkins(hid, days=7)

    return json.dumps({
        "ok": True,
        "habit_id": hid,
        "name": habit["name"],
        "frequency": habit.get("frequency", "daily"),
        "target_count": habit.get("target_count", 1),
        "streak": streak,
        "rate_7d": rate_7,
        "rate_30d": rate_30,
        "today_done": today_done,
        "recent_7_days": recent,
    }, ensure_ascii=False)


def tool_habit_list(**_: Any) -> str:
    if not _habits_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_HABITS_ENABLED=0"})

    all_habits = _store.load_all()
    active = [h for h in all_habits if h.get("active", True)]
    archived = [h for h in all_habits if not h.get("active", True)]

    return json.dumps({
        "ok": True,
        "active_count": len(active),
        "archived_count": len(archived),
        "habits": active,
    }, ensure_ascii=False)


def tool_habit_update(
    habit_id: str,
    name: str = "",
    frequency: str = "",
    target_count: Any = None,
    **_: Any,
) -> str:
    if not _habits_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_HABITS_ENABLED=0"})

    hid = (habit_id or "").strip()
    if not hid:
        return json.dumps({"ok": False, "error": "habit_id is required"})

    habit = _store.find_by_prefix(hid)
    if habit is None:
        return json.dumps({"ok": False, "error": f"Habit '{hid}' not found"})

    updated_fields: list[str] = []

    if name and name.strip():
        habit["name"] = name.strip()
        updated_fields.append("name")

    if frequency and frequency.strip():
        freq = frequency.strip().lower()
        if freq not in _VALID_FREQUENCIES:
            return json.dumps({
                "ok": False,
                "error": f"Invalid frequency '{frequency}'. Use: {', '.join(sorted(_VALID_FREQUENCIES))}",
            })
        habit["frequency"] = freq
        updated_fields.append("frequency")

    if target_count is not None:
        habit["target_count"] = max(1, int(target_count))
        updated_fields.append("target_count")

    if updated_fields:
        _store.save(habit)

    return json.dumps({
        "ok": True,
        "habit_id": habit["id"],
        "updated_fields": updated_fields,
    }, ensure_ascii=False)


def tool_habit_delete(habit_id: str, **_: Any) -> str:
    if not _habits_enabled():
        return json.dumps({"ok": False, "error": "BUTLER_HABITS_ENABLED=0"})

    habit = _find_habit_by_prefix_or_name(habit_id or "")
    if habit is None:
        return json.dumps({"ok": False, "error": f"Habit '{habit_id}' not found"})

    hid = habit["id"]
    name = habit.get("name", "")

    habit["active"] = False
    _store.save(habit)

    return json.dumps({
        "ok": True,
        "archived": hid,
        "name": name,
    }, ensure_ascii=False)


# ── WeChat Display ─────────────────────────────────────────────


def format_habits_for_wechat(arg: str = "") -> str:
    if not _habits_enabled():
        return "打卡功能未启用 (BUTLER_HABITS_ENABLED=0)"

    arg = (arg or "").strip()

    if arg.startswith("创建 ") or arg.startswith("新建 ") or arg.startswith("add "):
        name = arg.split(maxsplit=1)[1] if " " in arg else ""
        if name:
            raw = tool_habit_create(name=name)
            data = json.loads(raw)
            if data.get("ok"):
                return f"✅ 习惯已创建: {name} [{data['habit_id'][:4]}] ({_FREQ_LABELS.get(data['frequency'], '每日')})"
            return f"❌ {data.get('error', '创建失败')}"
        return "用法: /打卡 创建 <习惯名>"

    if arg.startswith("打 ") or arg.startswith("done ") or arg.startswith("完成 "):
        name = arg.split(maxsplit=1)[1] if " " in arg else ""
        if name:
            raw = tool_habit_checkin(habit_id=name)
            data = json.loads(raw)
            if data.get("ok"):
                streak_msg = f"🔥 连续 {data['streak']} 天" if data["streak"] > 1 else ""
                return f"✅ {data['habit']} 已打卡 ({data['date']})  {streak_msg}"
            return f"❌ {data.get('error', '打卡失败')}"
        return "用法: /打卡 打 <习惯名或ID>"

    return _format_habit_dashboard()


def _format_habit_dashboard() -> str:
    active = [h for h in _store.load_all() if h.get("active", True)]
    if not active:
        return "📋 暂无习惯\n\n创建: /打卡 创建 <习惯名>\n或对话中说「我要每天跑步」"

    today = _today_str()
    lines = [f"📋 习惯打卡 ({today})\n"]

    done_count = 0
    for h in active:
        hid = h["id"]
        ci = _get_checkin(hid, today)
        done = ci is not None
        if done:
            done_count += 1

        streak = _calc_streak(hid)
        status = "✅" if done else "⬜"
        streak_txt = f"🔥{streak}天" if streak > 1 else ""

        freq = _FREQ_LABELS.get(h.get("frequency", "daily"), "每日")
        lines.append(f"{status} {h['name']}  {streak_txt}  ({freq})")

    lines.append(f"\n今日完成: {done_count}/{len(active)}")
    lines.append("/打卡 打 <习惯名>  快速打卡")
    return "\n".join(lines)


# ── Registration ───────────────────────────────────────────────


def register_habit_tools(register: Callable[..., None]) -> None:
    if not _habits_enabled():
        return

    register(
        name="habit_create",
        description=(
            "为主人创建一个日常习惯追踪。如「每天喝8杯水」「每周运动3次」。"
            "支持 daily(每日) 和 weekly(每周) 频率。"
        ),
        schema={
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "习惯名称"},
                "frequency": {
                    "type": "string",
                    "enum": ["daily", "weekly"],
                    "description": "频率: daily(每日，默认) / weekly(每周)",
                },
                "target_count": {
                    "type": "integer",
                    "description": "每次目标次数（如喝水8杯），默认1",
                },
            },
            "required": ["name"],
        },
        handler=tool_habit_create,
        toolset="habits",
    )

    register(
        name="habit_checkin",
        description=(
            "【mutation·append】向 check-in 日志写入一次完成事件（habit_id、count、date）。"
            "场景：用户刚做完（「跑了步」「喝水打卡」）。"
            "仅返回写入确认；analytics 用 habit_stats。"
        ),
        schema={
            "type": "object",
            "properties": {
                "habit_id": {"type": "string", "description": "习惯 ID 或名称（支持前缀匹配）"},
                "count": {"type": "integer", "description": "打卡次数（默认1）"},
                "note": {"type": "string", "description": "可选备注（如：跑了5公里）"},
                "date": {"type": "string", "description": "日期 YYYY-MM-DD（默认今天）"},
            },
            "required": ["habit_id"],
        },
        handler=tool_habit_checkin,
        toolset="habits",
    )

    register(
        name="habit_stats",
        description=(
            "【metrics-only】streak、completion_rate、今日完成 flag。"
            "场景：连续几天、完成率。禁止输出名称清单。"
        ),
        schema={
            "type": "object",
            "properties": {
                "habit_id": {"type": "string", "description": "习惯 ID 或名称（可选，空=全部）"},
            },
        },
        handler=tool_habit_stats,
        toolset="habits",
    )

    register(
        name="habit_list",
        description=(
            "【roster-only】活跃习惯名称与 id 列表。"
            "场景：「有哪些习惯」。禁止 streak、rate、百分比。"
        ),
        schema={"type": "object", "properties": {}},
        handler=tool_habit_list,
        toolset="habits",
    )

    register(
        name="habit_update",
        description="修改习惯的名称、频率或目标次数。",
        schema={
            "type": "object",
            "properties": {
                "habit_id": {"type": "string", "description": "习惯 ID 或名称"},
                "name": {"type": "string", "description": "新名称"},
                "frequency": {
                    "type": "string",
                    "enum": list(_VALID_FREQUENCIES),
                    "description": "新频率",
                },
                "target_count": {"type": "integer", "description": "新目标次数"},
            },
            "required": ["habit_id"],
        },
        handler=tool_habit_update,
        toolset="habits",
    )

    register(
        name="habit_delete",
        description="归档（停用）一个习惯，保留历史打卡数据。",
        schema={
            "type": "object",
            "properties": {
                "habit_id": {"type": "string", "description": "习惯 ID 或名称"},
            },
            "required": ["habit_id"],
        },
        handler=tool_habit_delete,
        toolset="habits",
    )
