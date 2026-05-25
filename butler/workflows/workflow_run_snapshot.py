"""Persist workflow DAG run facts for rescue/diagnostics (Ansible subset)."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)


def workflow_run_snapshot_enabled() -> bool:
    return env_truthy("BUTLER_WORKFLOW_RUN_SNAPSHOT", default=True)


def workflow_run_path(workspace: Path, workflow_name: str, *, run_id: str = "") -> Path:
    base = Path(workspace).expanduser().resolve() / ".butler" / "workflow_runs"
    rid = (run_id or "latest").strip() or "latest"
    safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in workflow_name)[:64]
    return base / f"{safe}-{rid}.json"


def build_run_snapshot(
    workflow_name: str,
    graph: Any,
    *,
    session_key: str = "",
    run_id: str = "",
) -> dict[str, Any]:
    steps: dict[str, Any] = {}
    for step_id, result in getattr(graph, "nodes", {}).items():
        steps[step_id] = {
            "success": bool(getattr(result, "success", False)),
            "error": str(getattr(result, "error", "") or "")[:500],
            "response_preview": str(getattr(result, "response", "") or "")[:400],
        }
    failed = [sid for sid, s in steps.items() if not s.get("success")]
    return {
        "workflow": workflow_name,
        "run_id": run_id or "latest",
        "session_key": session_key,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "success": bool(getattr(graph, "success", False)),
        "error": str(getattr(graph, "error", "") or "")[:500],
        "execution_order": list(getattr(graph, "execution_order", []) or []),
        "failed_steps": failed,
        "steps": steps,
    }


def write_workflow_run_snapshot(
    workspace: Path,
    workflow_name: str,
    graph: Any,
    *,
    session_key: str = "",
    run_id: str = "",
) -> Path | None:
    if not workflow_run_snapshot_enabled():
        return None
    payload = build_run_snapshot(
        workflow_name,
        graph,
        session_key=session_key,
        run_id=run_id,
    )
    path = workflow_run_path(workspace, workflow_name, run_id=run_id or "latest")
    try:
        from butler.io.atomic_write import atomic_write_text

        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(
            path,
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        return path
    except OSError as exc:
        logger.debug("workflow_run snapshot write skipped: %s", exc)
        return None


__all__ = [
    "build_run_snapshot",
    "workflow_run_path",
    "workflow_run_snapshot_enabled",
    "write_workflow_run_snapshot",
]
