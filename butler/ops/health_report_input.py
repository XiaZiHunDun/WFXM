"""Shared types/helpers for health diagnostic assembly (Wave 4 cycle break)."""

from __future__ import annotations

from butler.contracts.health_report_input import HealthReportInput
from butler.core.best_effort import safe_best_effort


def format_build_uptime(start_ts: str) -> str:
    if not start_ts:
        return ""

    def _run() -> str:
        import datetime

        st = datetime.datetime.fromisoformat(start_ts)
        delta = datetime.datetime.now(tz=datetime.timezone.utc) - st
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        minutes = rem // 60
        return f"{hours}h {minutes}m"

    result = safe_best_effort(_run, label="health_report.build_uptime", default="")
    return result if isinstance(result, str) else ""


__all__ = ["HealthReportInput", "format_build_uptime"]
