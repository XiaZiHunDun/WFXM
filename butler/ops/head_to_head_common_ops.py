"""Head-to-head eval best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def seed_b9_workspace_read_state_safe(
    ws: Path,
    *,
    session_key: str,
    max_depth: int = 2,
) -> None:
    def _run() -> None:
        from butler.dev_engine.b9_delegate_gate import seed_b9_workspace_read_state

        seed_b9_workspace_read_state(ws, session_key=session_key, max_depth=max_depth)

    safe_best_effort(_run, label="head_to_head.seed_read_state", default=None)


def load_delegate_report_metrics_safe(
    task_id: str,
    session_key: str,
) -> dict[str, Any]:
    def _run() -> dict[str, Any]:
        from butler.report import get_last_report

        report = get_last_report(session_key)
        if report is None or str(getattr(report, "task_id", "") or "") != task_id:
            return {}
        out: dict[str, Any] = {
            "verify_passed": bool(getattr(report, "success", False)),
            "iterations": int(getattr(report, "iterations", 0) or 0),
            "tool_calls": int(getattr(report, "tool_calls", 0) or 0),
        }
        issues = getattr(report, "issues", None) or []
        if any("DEV_VERIFY_GATE" in str(i) for i in issues):
            out["verify_passed"] = False
        return out

    result = safe_best_effort(
        _run,
        label="head_to_head.delegate_report_metrics",
        default={},
    )
    return dict(result) if isinstance(result, dict) else {}
