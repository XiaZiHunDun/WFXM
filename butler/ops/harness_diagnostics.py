"""Harness-layer diagnostics (OpenClaw + OMO) for /诊断."""

from __future__ import annotations

from typing import Any
import logging


logger = logging.getLogger(__name__)

def format_harness_diagnostic_lines(
    health: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    lines: list[str] = []
    try:
        from butler.ops.openclaw_diagnostics import format_openclaw_diagnostic_lines

        lines.extend(format_openclaw_diagnostic_lines(health, session_key=session_key))
    except Exception as exc:
        logger.debug("format harness diagnostic lines skipped: %s", exc)
    lines.extend(_omo_lines(health, session_key=session_key))
    try:
        from butler.ops.registry_diagnostics import format_registry_diagnostic_lines

        reg_lines = format_registry_diagnostic_lines(health, session_key=session_key)
        if reg_lines:
            lines.extend(reg_lines)
    except Exception as exc:
        logger.debug("format harness diagnostic lines skipped: %s", exc)
    return lines


def _omo_lines(health: dict[str, Any] | None, *, session_key: str) -> list[str]:
    h = health or {}
    loop = h.get("loop") if isinstance(h.get("loop"), dict) else {}
    sk = str(session_key or h.get("session_key") or "").strip()
    lines: list[str] = []

    try:
        from butler.core.tool_pair_repair import tool_pair_repair_enabled

        lines.append(
            f"Tool-pair 修复: {'开' if tool_pair_repair_enabled() else '关'} (BUTLER_TOOL_PAIR_REPAIR)"
        )
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    rep = h.get("tool_pair_repair_count") or loop.get("tool_pair_repair_count")
    if rep:
        lines.append(f"Tool-pair 修复: 上轮插入 {rep} 条合成 tool 结果")

    if h.get("compaction_checkpoint_restored") or loop.get("compaction_checkpoint_restored"):
        model = h.get("compaction_checkpoint_model") or loop.get("compaction_checkpoint_model")
        todos = h.get("compaction_checkpoint_open_todos") or loop.get("compaction_checkpoint_open_todos")
        lines.append(
            f"压缩检查点: 已恢复"
            + (f" model={model}" if model else "")
            + (f" open_todos={todos}" if todos else "")
        )

    try:
        from butler.core.compaction_checkpoint import load_checkpoint

        if sk and load_checkpoint(sk):
            lines.append("压缩检查点: 磁盘有快照")
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    try:
        from butler.core.todo_continuation import max_continuations, todo_continuation_enabled

        if todo_continuation_enabled():
            cont = h.get("todo_continuation_count") or loop.get("todo_continuation_count")
            if cont:
                lines.append(f"待办续跑: 本 turn 续跑 {cont} 次 (上限 {max_continuations()})")
            else:
                lines.append(f"待办续跑: 开 (上限 {max_continuations()}/turn)")
        else:
            lines.append("待办续跑: 关")
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    if h.get("todo_continuation_stagnant") or loop.get("todo_continuation_stagnant"):
        lines.append("待办续跑: 上轮因停滞已停止")

    try:
        from butler.core.intent_keywords import intent_keywords_enabled

        lines.append(
            f"魔法词注入: {'开' if intent_keywords_enabled() else '关'} (BUTLER_INTENT_KEYWORDS)"
        )
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    try:
        from butler.delegate_category_resolver import list_categories

        cats = list_categories()
        if cats:
            lines.append(f"委派类别: {', '.join(cats)}")
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    try:
        from butler.core.hashline import hashline_read_enabled

        lines.append(
            f"Hashline 读: {'开' if hashline_read_enabled() else '关'} (BUTLER_HASHLINE_READ)"
        )
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    try:
        from butler.core.rules_engine import rules_engine_enabled, max_chars

        lines.append(
            f"规则引擎: {'开' if rules_engine_enabled() else '关'} (上限 {max_chars()} 字)"
        )
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    try:
        from butler.core.goal_loop import goal_loop_globally_enabled, is_goal_loop_active

        if is_goal_loop_active(sk) if sk else False:
            lines.append("目标循环: 本会话活跃 (/停止循环 结束)")
        else:
            lines.append(
                f"目标循环: {'全局开' if goal_loop_globally_enabled() else '默认关'} (BUTLER_GOAL_LOOP)"
            )
    except Exception as exc:
        logger.debug("omo lines skipped: %s", exc)
    return lines
