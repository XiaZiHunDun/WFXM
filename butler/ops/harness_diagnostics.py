"""Harness-layer diagnostics (OpenClaw + OMO) for /诊断."""

from __future__ import annotations

from typing import Any


def format_harness_diagnostic_lines(
    health: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    from butler.ops.harness_diagnostics_ops import (
        extend_openclaw_lines,
        extend_registry_lines,
    )

    lines: list[str] = []
    extend_openclaw_lines(lines, health, session_key=session_key)
    lines.extend(_omo_lines(health, session_key=session_key))
    extend_registry_lines(lines, health, session_key=session_key)
    return lines


def _omo_lines(health: dict[str, Any] | None, *, session_key: str) -> list[str]:
    from butler.ops.harness_diagnostics_ops import (
        append_compaction_checkpoint_disk_line,
        append_delegate_categories_line,
        append_goal_loop_line,
        append_hashline_line,
        append_intent_keywords_line,
        append_rules_engine_line,
        append_todo_continuation_line,
        append_tool_pair_repair_line,
    )

    h = health or {}
    loop = h.get("loop") if isinstance(h.get("loop"), dict) else {}
    sk = str(session_key or h.get("session_key") or "").strip()
    lines: list[str] = []

    append_tool_pair_repair_line(lines)
    rep = h.get("tool_pair_repair_count") or loop.get("tool_pair_repair_count")
    if rep:
        lines.append(f"Tool-pair 修复: 上轮插入 {rep} 条合成 tool 结果")

    if h.get("compaction_checkpoint_restored") or loop.get("compaction_checkpoint_restored"):
        model = h.get("compaction_checkpoint_model") or loop.get("compaction_checkpoint_model")
        todos = h.get("compaction_checkpoint_open_todos") or loop.get("compaction_checkpoint_open_todos")
        lines.append(
            "压缩检查点: 已恢复"
            + (f" model={model}" if model else "")
            + (f" open_todos={todos}" if todos else "")
        )

    append_compaction_checkpoint_disk_line(lines, sk)
    append_todo_continuation_line(lines, health)
    if h.get("todo_continuation_stagnant") or loop.get("todo_continuation_stagnant"):
        lines.append("待办续跑: 上轮因停滞已停止")

    append_intent_keywords_line(lines)
    append_delegate_categories_line(lines)
    append_hashline_line(lines)
    append_rules_engine_line(lines)
    append_goal_loop_line(lines, sk)
    return lines
