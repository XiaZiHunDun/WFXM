"""Built-in readonly runtime handlers (no subprocess)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.io.safe_load import safe_load_json


def run_builtin(handler: str, workspace: Path) -> dict[str, Any]:
    name = (handler or "").strip()
    if name == "builtin:workflow_state_digest":
        return _workflow_state_digest(workspace)
    if name == "builtin:memory_offline_consolidate":
        return _memory_offline_consolidate(workspace)
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
    # Audit R2-19: corrupt workflow_state.json used to silently
    # return a parse-error envelope. safe_load renames the corrupt
    # file for forensic retention, logs WARNING with exc_info, and
    # records the event for /诊断 — we still surface a parse error
    # to the user (the corruption event is logged separately).
    data = safe_load_json(path, default=None, kind="runtime_workflow_state")
    if not isinstance(data, dict):
        return {
            "success": False,
            "stdout": "",
            "stderr": "workflow_state.json unreadable or corrupt (see logs)",
            "summary": f"无法解析 workflow_state: 文件不可读或损坏",
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
    removed = mem.experience.prune_conversation_older_than(days)
    lines = [
        f"workspace: {workspace}",
        f"pruned_conversation_rows: {removed}",
        f"max_age_days: {days}",
    ]
    summary = f"记忆离线整理：删除 {removed} 条过期 conversation 经验（>{days:.0f} 天）"
    return {
        "success": True,
        "stdout": "\n".join(lines),
        "stderr": "",
        "summary": summary,
    }
