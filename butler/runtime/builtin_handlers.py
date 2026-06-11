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
    status = data.get("project_status") if isinstance(data.get("project_status"), dict) else {}
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
