"""Terminal sandbox diagnostics best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


def default_project_workspace_safe() -> Path | None:
    def _run() -> Path:
        from butler.tools.path_safety import _default_project_workspace

        return Path(_default_project_workspace())

    result = safe_best_effort(
        _run,
        label="terminal_sandbox_diagnostics.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def append_sandbox_metrics_lines_safe(lines: list[str]) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import snapshot_global

        counters = snapshot_global().get("counters") or {}
        run = sum(v for k, v in counters.items() if k.startswith("terminal_sandbox_run"))
        fail = sum(
            v for k, v in counters.items() if k.startswith("terminal_sandbox_failure")
        )
        esc = counters.get("terminal_sandbox_escalation_approved", 0)
        fallback = counters.get("terminal_sandbox_unavailable_fallback", 0)
        if run or fail or esc or fallback:
            lines.append(
                f"  累计: 沙箱执行 {run} | 沙箱失败 {fail} | 沙箱外批准 {esc} | 无 bwrap 降级 {fallback}"
            )

    safe_best_effort(_run, label="terminal_sandbox_diagnostics.metrics", default=None)


def append_env_profile_lines_safe(lines: list[str], *, bwrap_available: bool) -> None:
    def _run() -> None:
        from butler.ops.env_profiles import (
            current_env_profile,
            profile_expectation,
            profile_mismatch_messages,
        )

        prof_name = current_env_profile()
        if prof_name:
            exp = profile_expectation(prof_name)
            if exp:
                lines.append(f"  Env profile: {prof_name} — {exp.description}")
        for msg in profile_mismatch_messages(bwrap_available=bwrap_available):
            lines.append(f"  ⚠ {msg}")

    safe_best_effort(_run, label="terminal_sandbox_diagnostics.env_profile", default=None)
