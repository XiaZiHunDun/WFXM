"""Hook telemetry best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def inc_hook_run_metric_safe(
    *,
    event: str,
    exit_code: int | None,
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        outcome = "ok" if exit_code == 0 else "fail" if exit_code is not None else "unknown"
        inc(
            "hook_run",
            labels={"event": str(event or "?")[:32], "outcome": outcome},
            session_key=session_key,
        )

    safe_best_effort(_run, label="hook_telemetry.inc", default=None)


def reset_hook_session_metrics_safe(session_key: str) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import reset_session

        reset_session(session_key)

    safe_best_effort(_run, label="hook_telemetry.reset_session", default=None)


def load_hooks_config_summary_safe(workspace: Any = None) -> str | None:
    def _run() -> str:
        from butler.hooks.loader import load_hooks_config

        ws = Path(workspace) if workspace is not None else None
        rules = load_hooks_config(ws)
        if not rules:
            return "未配置"
        counts: dict[str, int] = {}
        for rule in rules:
            counts[rule.event] = counts.get(rule.event, 0) + 1
        return ", ".join(f"{ev}×{n}" for ev, n in sorted(counts.items()))

    result = safe_best_effort(
        _run,
        label="hook_telemetry.config_summary",
        default=None,
    )
    return str(result) if result is not None else None


def resolve_hook_workspace_safe() -> Any | None:
    def _run() -> Any:
        from butler.hooks.runner import _resolve_workspace

        return _resolve_workspace()

    return safe_best_effort(
        _run,
        label="hook_telemetry.resolve_workspace",
        default=None,
    )
