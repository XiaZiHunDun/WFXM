"""Format Owner /简报 four-block layout (PROD-P1-02)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

_OVERNIGHT_HOURS = 18


def _parse_run_finished_at(raw: Any) -> datetime | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            return datetime.fromisoformat(text.replace("Z", "+00:00"))
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def format_overnight_jobs_lines(project_name: str) -> list[str]:
    """Lines for /简报 block「昨夜 job」— runs in the last ~18h."""
    name = str(project_name or "").strip()
    if not name:
        return ["  未选择项目 → /切换"]

    try:
        from butler.runtime.service import list_jobs_status, runtime_enabled

        if not runtime_enabled():
            return ["  Runtime 未启用（BUTLER_RUNTIME_ENABLED=0）"]
        rows = list_jobs_status(name)
    except Exception as exc:
        logger.debug("overnight jobs brief skipped: %s", exc)
        return ["  （定时任务状态暂不可用）"]

    if not rows:
        return ["  无 runtime/jobs.yaml"]

    cutoff = datetime.now(timezone.utc) - timedelta(hours=_OVERNIGHT_HOURS)
    recent: list[str] = []
    for row in rows:
        finished = _parse_run_finished_at(row.get("last_at"))
        if finished is None or finished < cutoff:
            continue
        jid = str(row.get("id") or "?")
        mark = "✓" if row.get("last_success") else "✗"
        when = finished.astimezone(timezone.utc).strftime("%m-%d %H:%M")
        recent.append(f"  · {jid} {mark} ({when} UTC)")

    if recent:
        return recent[:5]

    enabled = [r for r in rows if r.get("enabled", True)]
    if not enabled:
        return ["  定时任务均已关闭"]
    return [
        f"  昨夜无执行记录（{len(enabled)} 个任务在册）",
        "  查看：/运行 list · 手动 /运行 <id>",
    ]


__all__ = ["format_overnight_jobs_lines"]
