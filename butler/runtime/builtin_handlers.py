"""Built-in readonly runtime handlers (no subprocess)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_builtin(handler: str, workspace: Path) -> dict[str, Any]:
    name = (handler or "").strip()
    if name == "builtin:workflow_state_digest":
        return _workflow_state_digest(workspace)
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
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "success": False,
            "stdout": "",
            "stderr": str(exc),
            "summary": f"无法解析 workflow_state: {exc}",
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
