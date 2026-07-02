"""Best-effort helpers for informational slash commands (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def append_pim_store_usage_line(
    lines: list[str],
    *,
    label: str,
    store: Any,
    limit: int,
) -> None:
    before = len(lines)

    def _run() -> None:
        count = store.count()
        pct = int(count / limit * 100) if limit else 0
        bar = "█" * (pct // 10) + "░" * (10 - pct // 10)
        lines.append(f"{label}: {count}/{limit} ({pct}%) {bar}")

    safe_best_effort(_run, label=f"info_commands.pim.{label}", default=None)
    if len(lines) == before:
        lines.append(f"{label}: 读取失败")


def append_reminder_summary_line(lines: list[str]) -> None:
    before = len(lines)

    def _run() -> None:
        from butler.tools.reminder import _load_all

        reminders = _load_all()
        pending = sum(1 for r in reminders if r.get("status") == "pending")
        fired = sum(1 for r in reminders if r.get("status") == "fired")
        lines.append(f"提醒: {pending} 待触发 / {fired} 已触发")

    safe_best_effort(_run, label="info_commands.pim.reminders", default=None)
    if len(lines) == before:
        lines.append("提醒: 读取失败")


def record_brief_view_safe(*, session_key: str) -> None:
    def _run() -> None:
        from butler.ops.owner_pmf_metrics import record_brief_view

        record_brief_view(session_key=session_key)

    safe_best_effort(_run, label="info_commands.brief_view", default=None)
