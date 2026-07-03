"""Runtime failure streak persistence best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def load_failure_streaks_safe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}

    def _run() -> dict[str, Any]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    result = safe_best_effort(_run, label="failure_tracker.load_streaks", default={})
    return result if isinstance(result, dict) else {}


def push_failure_streak_alert_safe(
    project_name: str,
    job_id: str,
    streak: int,
    audit_path: str,
) -> bool:
    try:
        from butler.runtime.notify import push_runtime_message

        body = (
            f"任务 {job_id} 已连续失败 {streak} 次。\n"
            f"请检查日志或执行: butler runtime run {job_id} --project {project_name}\n"
        )
        if audit_path:
            body += f"审计: {audit_path}"
        return bool(
            push_runtime_message(
                f"[Butler] {project_name} runtime 连续失败",
                body[:1200],
            )
        )
    except Exception as exc:
        logger.warning("Failure streak alert push failed: %s", exc)
        return False
