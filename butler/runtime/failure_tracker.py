"""Track consecutive runtime job failures and optional Owner alert (no auto-retry)."""

from __future__ import annotations

from butler.env_parse import int_env
import json
import time
from pathlib import Path
from typing import Any, cast

from butler.config import get_butler_home

_STREAKS_FILE = "runtime/failure_streaks.json"


def _streaks_path() -> Path:
    return Path(get_butler_home() / _STREAKS_FILE)


def _alert_threshold() -> int:
    try:
        return int(int_env("BUTLER_RUNTIME_FAIL_ALERT_STREAK", 3, min=1))
    except ValueError:
        return 3


def _load_streaks() -> dict[str, Any]:
    from butler.runtime.failure_tracker_ops import load_failure_streaks_safe

    return cast(dict[str, Any], load_failure_streaks_safe(_streaks_path()))


def _save_streaks(data: dict[str, Any]) -> None:
    path = _streaks_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=0), encoding="utf-8")


def _job_key(project_name: str, job_id: str) -> str:
    return f"{project_name.strip()}::{job_id.strip()}"


def record_job_outcome(
    project_name: str,
    job_id: str,
    *,
    success: bool,
    audit_path: str = "",
) -> dict[str, Any]:
    """
    Update failure streak; optionally push WeChat when streak reaches threshold.

    Returns dict with ``streak``, ``alerted`` (bool).
    """
    key = _job_key(project_name, job_id)
    data = _load_streaks()
    entry_raw = data.get(key)
    entry = entry_raw if isinstance(entry_raw, dict) else {}
    threshold = _alert_threshold()

    if success:
        if entry:
            data.pop(key, None)
            _save_streaks(data)
        return {"streak": 0, "alerted": False, "threshold": threshold}

    streak = int(entry.get("streak") or 0) + 1
    last_alert_at = float(entry.get("last_alert_at") or 0)
    entry = {
        "streak": streak,
        "last_failure_at": time.time(),
        "last_audit": audit_path,
        "last_alert_at": last_alert_at,
    }
    data[key] = entry
    _save_streaks(data)

    alerted = False
    if streak >= threshold and streak == threshold:
        alerted = _push_streak_alert(project_name, job_id, streak, audit_path)
        if alerted:
            entry["last_alert_at"] = time.time()
            data[key] = entry
            _save_streaks(data)

    return {"streak": streak, "alerted": alerted, "threshold": threshold}


def _push_streak_alert(
    project_name: str,
    job_id: str,
    streak: int,
    audit_path: str,
) -> bool:
    from butler.runtime.failure_tracker_ops import push_failure_streak_alert_safe

    return bool(
        push_failure_streak_alert_safe(
            project_name,
            job_id,
            streak,
            audit_path,
        )
    )


def list_active_streaks(*, min_streak: int = 1) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, entry in _load_streaks().items():
        if not isinstance(entry, dict):
            continue
        streak = int(entry.get("streak") or 0)
        if streak < min_streak:
            continue
        if "::" in key:
            proj, jid = key.split("::", 1)
        else:
            proj, jid = key, ""
        out.append(
            {
                "project": proj,
                "job_id": jid,
                "streak": streak,
                "last_audit": entry.get("last_audit"),
            }
        )
    out.sort(key=lambda r: (-int(r["streak"]), r["project"], r["job_id"]))
    return out


def format_failure_streak_lines() -> list[str]:
    rows = list_active_streaks()
    if not rows:
        return []
    lines = [f"  runtime 连续失败: {len(rows)} 项（阈值 {_alert_threshold()} 次告警）"]
    for r in rows[:5]:
        audit = r.get("last_audit") or ""
        tail = f" | {audit}" if audit else ""
        lines.append(f"    {r['project']}/{r['job_id']}: {r['streak']} 次{tail}")
    return lines
