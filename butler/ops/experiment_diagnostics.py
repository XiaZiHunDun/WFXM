"""Experiment ledger lines for /诊断."""

from __future__ import annotations

from pathlib import Path

from butler.experiments.ledger import best_record, experiments_ledger_path, list_recent
from butler.experiments.mode import experiment_mode_enabled
import logging


logger = logging.getLogger(__name__)

def format_experiment_diagnostic_lines(
    workspace: Path | None,
    *,
    limit: int = 5,
) -> list[str]:
    if workspace is None:
        return []
    ws = Path(workspace).expanduser().resolve()
    path = experiments_ledger_path(ws)
    lines = ["实验 / harness:"]
    lines.append(f"  研究模式 BUTLER_EXPERIMENT_MODE: {'开' if experiment_mode_enabled() else '关'}")
    if not path.is_file():
        lines.append("  账本: 无 (.butler/experiments.tsv)")
        return lines
    rows = list_recent(ws, limit=limit)
    lines.append(f"  账本: {path.relative_to(ws) if path.is_relative_to(ws) else path} ({len(rows)} 最近行)")
    best = best_record(ws)
    if best:
        lines.append(
            f"  最佳 keep: {best.get('metric_name')}={best.get('metric_value')} "
            f"@ {str(best.get('git_sha') or '')[:12]}"
        )
    for row in rows[-limit:]:
        lines.append(
            f"  · {row.get('status', '?')} {row.get('metric_name')}={row.get('metric_value')} "
            f"sha={str(row.get('git_sha') or '')[:8]} "
            f"{(row.get('hypothesis') or '')[:40]}"
        )
    try:
        from butler.experiments.crash_guard import consecutive_crash_count, crash_block_threshold

        streak = consecutive_crash_count(ws)
        if streak:
            lines.append(
                f"  连续 crash: {streak}（阻断阈值 {crash_block_threshold()}）"
            )
    except Exception as exc:
        logger.debug("format experiment diagnostic lines skipped: %s", exc)
    return lines


def format_experiment_diagnostic_lines_for_project(
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
        return format_experiment_diagnostic_lines(Path(proj.workspace), limit=limit)
    except Exception:
        return []


__all__ = [
    "format_experiment_diagnostic_lines",
    "format_experiment_diagnostic_lines_for_project",
]
