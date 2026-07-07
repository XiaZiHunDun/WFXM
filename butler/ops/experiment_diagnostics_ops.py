"""Experiment diagnostics best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import cast

import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def append_crash_guard_lines_safe(
    lines: list[str],
    workspace: Path,
) -> None:
    try:
        from butler.experiments.crash_guard import consecutive_crash_count, crash_block_threshold

        streak = consecutive_crash_count(workspace)
        if streak:
            lines.append(
                f"  连续 crash: {streak}（阻断阈值 {crash_block_threshold()}）"
            )
    except Exception as exc:
        logger.debug("format experiment diagnostic lines skipped: %s", exc)


def format_experiment_diagnostic_lines_for_project_safe(
    project_name: str,
    *,
    limit: int = 5,
) -> list[str]:
    name = str(project_name or "").strip()
    if not name:
        return []
    try:
        from butler.project.manager import get_project_manager

        proj = get_project_manager().get_project(name)
        if proj is None:
            return []
        from butler.ops.experiment_diagnostics import format_experiment_diagnostic_lines

        return cast(list[str], format_experiment_diagnostic_lines(Path(proj.workspace), limit=limit))
    except Exception:
        return []
