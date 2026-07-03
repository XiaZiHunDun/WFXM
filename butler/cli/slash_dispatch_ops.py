"""Slash dispatch report load best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any


def get_last_report_safe() -> tuple[Any, str | None]:
    """Return ``(report, user_error)``; ``user_error`` set when load fails."""
    try:
        from butler.report import get_last_report

        return get_last_report(), None
    except Exception:
        return None, "报告系统不可用"
