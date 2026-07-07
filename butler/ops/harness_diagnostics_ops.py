"""Harness diagnostic probes (P0-A best-effort)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


from butler.ops.openclaw_diagnostics import format_openclaw_diagnostic_lines
from butler.ops.registry_diagnostics import format_registry_diagnostic_lines
from butler.core.tool_pair_repair import tool_pair_repair_enabled
from butler.core.compaction_checkpoint import load_checkpoint
from butler.core.todo_continuation import (
    max_continuations,
    todo_continuation_enabled,
)
from butler.core.intent_keywords import intent_keywords_enabled
from butler.delegate.category_resolver import list_categories
from butler.core.hashline import hashline_read_enabled
from butler.core.rules_engine import (
    max_chars,
    rules_engine_enabled,
)
from butler.core.goal_loop import (
    goal_loop_globally_enabled,
    is_goal_loop_active,
)

def extend_openclaw_lines(
    lines: list[str],
    health: dict[str, Any] | None,
    *,
    session_key: str,
) -> None:
    def _run() -> None:

        lines.extend(format_openclaw_diagnostic_lines(health, session_key=session_key))

    safe_best_effort(_run, label="harness_diagnostics.openclaw", default=None)


def extend_registry_lines(
    lines: list[str],
    health: dict[str, Any] | None,
    *,
    session_key: str,
) -> None:
    def _run() -> None:

        reg_lines = format_registry_diagnostic_lines(health, session_key=session_key)
        if reg_lines:
            lines.extend(reg_lines)

    safe_best_effort(_run, label="harness_diagnostics.registry", default=None)


def append_tool_pair_repair_line(lines: list[str]) -> None:
    def _build() -> str:

        return (
            f"Tool-pair 修复: {'开' if tool_pair_repair_enabled() else '关'} "
            "(BUTLER_TOOL_PAIR_REPAIR)"
        )

    line = safe_best_effort(_build, label="harness_diagnostics.tool_pair", default="")
    if isinstance(line, str) and line:
        lines.append(line)


def append_compaction_checkpoint_disk_line(lines: list[str], session_key: str) -> None:
    def _run() -> None:

        if session_key and load_checkpoint(session_key):
            lines.append("压缩检查点: 磁盘有快照")

    safe_best_effort(_run, label="harness_diagnostics.compaction_checkpoint", default=None)


def append_todo_continuation_line(lines: list[str], health: dict[str, Any] | None) -> None:
    def _run() -> None:

        h = health or {}
        loop = h.get("loop") if isinstance(h.get("loop"), dict) else {}
        if todo_continuation_enabled():
            cont = h.get("todo_continuation_count") or loop.get("todo_continuation_count")
            if cont:
                lines.append(f"待办续跑: 本 turn 续跑 {cont} 次 (上限 {max_continuations()})")
            else:
                lines.append(f"待办续跑: 开 (上限 {max_continuations()}/turn)")
        else:
            lines.append("待办续跑: 关")

    safe_best_effort(_run, label="harness_diagnostics.todo_continuation", default=None)


def append_intent_keywords_line(lines: list[str]) -> None:
    def _build() -> str:

        return (
            f"魔法词注入: {'开' if intent_keywords_enabled() else '关'} "
            "(BUTLER_INTENT_KEYWORDS)"
        )

    line = safe_best_effort(_build, label="harness_diagnostics.intent_keywords", default="")
    if isinstance(line, str) and line:
        lines.append(line)


def append_delegate_categories_line(lines: list[str]) -> None:
    def _run() -> None:

        cats = list_categories()
        if cats:
            lines.append(f"委派类别: {', '.join(cats)}")

    safe_best_effort(_run, label="harness_diagnostics.delegate_categories", default=None)


def append_hashline_line(lines: list[str]) -> None:
    def _build() -> str:

        return f"Hashline 读: {'开' if hashline_read_enabled() else '关'} (BUTLER_HASHLINE_READ)"

    line = safe_best_effort(_build, label="harness_diagnostics.hashline", default="")
    if isinstance(line, str) and line:
        lines.append(line)


def append_rules_engine_line(lines: list[str]) -> None:
    def _build() -> str:

        return (
            f"规则引擎: {'开' if rules_engine_enabled() else '关'} "
            f"(上限 {max_chars()} 字)"
        )

    line = safe_best_effort(_build, label="harness_diagnostics.rules_engine", default="")
    if isinstance(line, str) and line:
        lines.append(line)


def append_goal_loop_line(lines: list[str], session_key: str) -> None:
    def _build() -> str:

        if session_key and is_goal_loop_active(session_key):
            return "目标循环: 本会话活跃 (/停止循环 结束)"
        return (
            f"目标循环: {'全局开' if goal_loop_globally_enabled() else '默认关'} "
            "(BUTLER_GOAL_LOOP)"
        )

    line = safe_best_effort(_build, label="harness_diagnostics.goal_loop", default="")
    if isinstance(line, str) and line:
        lines.append(line)
