"""Persist AgentReport snapshots under ~/.butler/runtime/reports/."""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.report import AgentReport, Change


def _reports_root() -> Path:
    from butler.config import get_butler_settings

    root = get_butler_settings().butler_home / "runtime" / "reports"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _slug_session_key(session_key: str) -> str:
    raw = str(session_key or "default").strip() or "default"
    return re.sub(r"[^\w\-.]+", "_", raw)[:120]


def persist_report(
    report: AgentReport,
    *,
    session_key: str = "",
    task_id: str = "",
) -> Path:
    key = _slug_session_key(session_key)
    payload: dict[str, Any] = {
        "session_key": str(session_key or "").strip() or "default",
        "task_id": str(task_id or "").strip(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        **report.to_dict(),
        "iterations": report.iterations,
        "tool_calls": report.tool_calls,
        "tokens_used": report.tokens_used,
        "elapsed_seconds": report.elapsed_seconds,
    }
    path = _reports_root() / f"{key}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_persisted_report(session_key: str = "") -> AgentReport | None:
    key = _slug_session_key(session_key)
    path = _reports_root() / f"{key}.json"
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    report = AgentReport.from_dict(data)
    report.iterations = int(data.get("iterations") or 0)
    report.tool_calls = int(data.get("tool_calls") or 0)
    report.tokens_used = int(data.get("tokens_used") or 0)
    report.elapsed_seconds = float(data.get("elapsed_seconds") or 0.0)
    return report
