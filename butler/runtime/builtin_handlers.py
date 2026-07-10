"""Built-in readonly runtime handlers (no subprocess)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.io.safe_load import quarantine_corrupt_file, record_state_file_corruption

logger = logging.getLogger(__name__)


def run_builtin(handler: str, workspace: Path) -> dict[str, Any]:
    name = (handler or "").strip()
    if name == "builtin:workflow_state_digest":
        return _workflow_state_digest(workspace)
    if name == "builtin:memory_offline_consolidate":
        return _memory_offline_consolidate(workspace)
    if name == "builtin:experience_mining_weekly":
        return _experience_mining_weekly(workspace)
    if name == "builtin:todos_pending_drift":
        return _todos_pending_drift(workspace)
    if name == "builtin:consistency_weekly_summary":
        return _consistency_weekly_summary(workspace)
    raise ValueError(f"Unknown builtin handler: {handler}")


def _workflow_state_digest(workspace: Path) -> dict[str, Any]:
    path = workspace / "novel-factory" / "workflow_state.json"
    if not path.is_file():
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Missing {path}",
            "summary": "未找到 workflow_state.json",
        }
    # Audit R2-19: corrupt workflow_state.json used to silently swallow
    # the error after losing the file. We do an inline try/except (rather
    # than going through safe_load_json) so we can preserve the original
    # user-facing ``str(exc)`` detail in the stderr/summary envelope
    # while still routing corruption through the forensic + diagnostics
    # pipeline via the public safe_load helpers.
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        backup = quarantine_corrupt_file(path)
        logger.warning(
            "Corrupt workflow_state.json %s, renamed to %s: %s",
            path, backup or "<rename-failed>", exc,
            exc_info=exc,
        )
        record_state_file_corruption(
            "runtime_workflow_state", path, str(exc), backup,
        )
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "summary": f"无法解析 workflow_state: {exc}",
        }
    if not isinstance(data, dict):
        return {
            "success": False,
            "stdout": "",
            "stderr": "workflow_state.json top-level is not an object",
            "summary": "无法解析 workflow_state: 顶层不是对象",
        }

    phase = data.get("current_phase") or "?"
    step = data.get("current_step") or "?"
    status_raw = data.get("project_status")
    status: dict[str, Any] = status_raw if isinstance(status_raw, dict) else {}
    pname = status.get("name") or "?"
    pphase = status.get("phase") or "?"
    summary = (
        f"项目: {pname}\n"
        f"current_phase: {phase}\n"
        f"current_step: {step}\n"
        f"project_status.phase: {pphase}"
    )
    return {
        "success": True,
        "stdout": summary,
        "stderr": "",
        "summary": summary,
    }


def _memory_offline_consolidate(workspace: Path) -> dict[str, Any]:
    """Prune stale conversation experience rows (OpenClaw memory-dreaming subset)."""
    import os

    from butler.config import get_butler_home
    from butler.memory.butler_memory import ButlerMemory

    raw = os.getenv("BUTLER_EXPERIENCE_PRUNE_DAYS", "30").strip()
    if raw in ("0", "off", "false", "no"):
        return {
            "success": True,
            "stdout": "BUTLER_EXPERIENCE_PRUNE_DAYS=0，跳过 experience 修剪",
            "stderr": "",
            "summary": "记忆离线整理：已跳过（修剪关闭）",
        }
    try:
        days = float(raw)
    except ValueError:
        days = 30.0

    mem = ButlerMemory(get_butler_home())
    purge = mem.prune_conversation_older_than(days)
    removed = int(purge.get("removed_rows") or 0)
    removed_vectors = int(purge.get("removed_vectors") or 0)
    lines = [
        f"workspace: {workspace}",
        f"pruned_conversation_rows: {removed}",
        f"pruned_conversation_vectors: {removed_vectors}",
        f"max_age_days: {days}",
    ]
    summary = (
        f"记忆离线整理：删除 {removed} 条过期 conversation 经验（>{days:.0f} 天）"
        + (f"，同步 {removed_vectors} 条向量" if removed_vectors else "")
    )
    return {
        "success": True,
        "stdout": "\n".join(lines),
        "stderr": "",
        "summary": summary,
    }


def _experience_mining_weekly(workspace: Path) -> dict[str, Any]:
    """D3-6 weekly mining: scan → review → pending queue (no default auto-ingest)."""
    from butler.memory.experience_mining import (
        default_mining_days,
        format_pipeline_report,
        mining_enabled,
        run_pipeline,
    )

    if not mining_enabled():
        return {
            "success": True,
            "stdout": "BUTLER_EXPERIENCE_MINING=0，跳过经验挖掘",
            "stderr": "",
            "summary": "经验挖掘：已跳过（挖掘关闭）",
        }

    days = default_mining_days()
    result = run_pipeline(workspace, days=days, auto_ingest=False)
    report_text = format_pipeline_report(result)
    return {
        "success": True,
        "stdout": report_text,
        "stderr": "",
        "summary": report_text,
    }


def _todos_pending_drift(workspace: Path) -> dict[str, Any]:
    """Read-only drift report between .butler/todos.json and MEMORY.md ## Pending."""
    from butler.tools.project_todos_drift_ops import collect_todos_pending_drift

    drift = collect_todos_pending_drift(workspace)
    summary = _format_drift_summary(drift)
    return {
        "success": True,
        "stdout": summary,
        "stderr": "",
        "summary": summary,
    }


def _format_drift_summary(drift: dict[str, Any]) -> str:
    """Compact Chinese summary for WeChat push; cap samples per category."""
    counts = drift.get("counts", {})
    lines = [
        "待办 vs Pending 漂移：",
        f"  drift: {counts.get('drift_total', 0)} (todos_open={counts.get('todos_open', 0)}, "
        f"todos_completed={counts.get('todos_completed', 0)}, pending_open={counts.get('pending_open', 0)})",
    ]

    completed = drift.get("completed_todo_with_open_pending", [])
    if completed:
        lines.append(f"  · todo 已完成但 Pending 仍开（疑似 stale，建议 /拒绝记忆）: {len(completed)}")
        for row in completed[:5]:
            lines.append(
                f"      [{row['todo'].get('id', '')}] {row['pending'].get('content', '')[:60]}"
            )

    pending_no_todo = drift.get("pending_with_no_todo", [])
    if pending_no_todo:
        lines.append(f"  · Pending 未跟踪（无对应 todo，建议手动建 todo）: {len(pending_no_todo)}")
        for row in pending_no_todo[:5]:
            lines.append(
                f"      [{row['pending'].get('timestamp', '')}] {row['pending'].get('content', '')[:60]}"
            )

    open_no_pending = drift.get("open_todo_with_no_pending", [])
    if open_no_pending:
        lines.append(f"  · todo 未走 owner 审核（无 Pending，建议 /批准记忆）: {len(open_no_pending)}")
        for row in open_no_pending[:5]:
            lines.append(
                f"      [{row['todo'].get('id', '')}] {row['todo'].get('content', '')[:60]}"
            )

    if counts.get("drift_total", 0) == 0:
        lines.append("  · 一致 ✓")

    out = "\n".join(lines)
    if len(out) > 700:
        out = out[:697] + "…"
    return out


def _consistency_weekly_summary(workspace: Path) -> dict[str, Any]:
    """Read-only consistency JSON digest for WeChat push (P2 #9)."""
    from butler.tools.consistency_summary_ops import summarize_consistency_report

    data = summarize_consistency_report(workspace)
    if not data.get("loaded"):
        msg = f"consistency 摘要：未找到 {data.get('path')}"
        return {
            "success": False,
            "stdout": "",
            "stderr": data.get("error") or "missing report",
            "summary": msg,
        }
    summary = _format_consistency_summary(data)
    return {
        "success": True,
        "stdout": summary,
        "stderr": "",
        "summary": summary,
    }


def _format_consistency_summary(data: dict[str, Any]) -> str:
    """Compact Chinese summary for WeChat push; cap 800 chars."""
    totals = data.get("totals", {})
    by_check = data.get("by_check", {})
    verdict = data.get("verdict", "pass")
    verdict_label = {"pass": "通过 ✓", "warn": "有条件 ⚠", "fail": "失败 ✗"}.get(verdict, verdict)

    duration = float(data.get("duration_seconds") or 0.0)
    lines = [
        f"consistency 周报：P0={totals.get('P0', 0)} P1={totals.get('P1', 0)} P2={totals.get('P2', 0)}"
        f"（章节 {data.get('chapter_range', '?')}，耗时 {duration:.0f}s）— {verdict_label}",
    ]

    check_order = ("naming", "integrity", "duplicates", "character", "timeline")
    check_lines = [f"  · {name}: {by_check.get(name, 0)} 处" for name in check_order]
    lines.extend(check_lines)

    top_p1 = data.get("top_p1") or []
    if top_p1:
        lines.append(f"  · top P1（{len(top_p1)}/{totals.get('P1', 0)}）:")
        for row in top_p1[:5]:
            ch = row.get("chapter", 0)
            ent = row.get("entity", "") or "—"
            msg = row.get("message", "")[:60]
            lines.append(f"      [chapter {ch}] {ent} · {msg}")

    age = data.get("age_days")
    if age is not None and age > 7:
        lines.append(f"  · ⚠ 报告陈旧（{age:.1f} 天前）")

    if totals.get("total", 0) == 0:
        lines.append("  · 全绿 ✓")

    out = "\n".join(lines)
    if len(out) > 800:
        out = out[:797] + "…"
    return out
