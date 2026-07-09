"""Per-project maturity stats — gates delete_file until enough edit/dev history."""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from butler.env_parse import int_env
from butler.project.manager import get_project_manager

_LOCK = threading.Lock()

DEFAULT_MIN_LINES_MODIFIED = 20_000
DEFAULT_MIN_DEV_DELEGATE_RUNS = 300


def min_lines_modified_for_delete() -> int:
    return int_env(
        "BUTLER_PROJECT_DELETE_MIN_LINES",
        DEFAULT_MIN_LINES_MODIFIED,
        min=0,
    )


def min_dev_delegates_for_delete() -> int:
    return int_env(
        "BUTLER_PROJECT_DELETE_MIN_DEV_DELEGATES",
        DEFAULT_MIN_DEV_DELEGATE_RUNS,
        min=0,
    )


def project_delete_gate_enabled() -> bool:
    import os

    return os.getenv("BUTLER_PROJECT_DELETE_MATURITY_GATE", "1").strip().lower() not in (
        "0",
        "false",
        "off",
    )


@dataclass
class ProjectMaturityStats:
    lines_modified_total: int = 0
    dev_delegate_runs: int = 0
    updated_at: str = ""

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> ProjectMaturityStats:
        return cls(
            lines_modified_total=int(raw.get("lines_modified_total") or 0),
            dev_delegate_runs=int(raw.get("dev_delegate_runs") or 0),
            updated_at=str(raw.get("updated_at") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines_modified_total": self.lines_modified_total,
            "dev_delegate_runs": self.dev_delegate_runs,
            "updated_at": self.updated_at,
        }


def _stats_path(project_name: str) -> Path | None:
    proj = get_project_manager().get_project(project_name)
    if proj is None:
        matched = get_project_manager().resolve_project_name(project_name)
        if matched:
            proj = get_project_manager().get_project(matched)
    if proj is None:
        return None
    root = (proj.workspace / ".butler").resolve(strict=False)
    return root / "project_maturity.json"


def load_project_maturity(project_name: str) -> ProjectMaturityStats:
    path = _stats_path(project_name)
    if path is None or not path.is_file():
        return ProjectMaturityStats()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ProjectMaturityStats()
    if not isinstance(data, dict):
        return ProjectMaturityStats()
    return ProjectMaturityStats.from_dict(data)


def save_project_maturity(project_name: str, stats: ProjectMaturityStats) -> None:
    path = _stats_path(project_name)
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    stats.updated_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    path.write_text(
        json.dumps(stats.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def project_for_resolved_path(resolved: Path) -> str | None:
    pm = get_project_manager()
    try:
        target = resolved.resolve(strict=False)
    except OSError:
        return None
    for proj in pm.list_projects():
        try:
            ws = proj.workspace.expanduser().resolve(strict=False)
        except OSError:
            continue
        try:
            if target.is_relative_to(ws):
                return proj.name
        except ValueError:
            continue
    return None


def delete_allowed_for_project(project_name: str) -> bool:
    if not project_delete_gate_enabled():
        return True
    stats = load_project_maturity(project_name)
    return (
        stats.lines_modified_total >= min_lines_modified_for_delete()
        and stats.dev_delegate_runs >= min_dev_delegates_for_delete()
    )


def delete_allowed_for_path(resolved: Path) -> tuple[bool, str]:
    """Return (allowed, reason). Non-project paths are not maturity-gated."""
    if not project_delete_gate_enabled():
        return True, ""
    name = project_for_resolved_path(resolved)
    if not name:
        return True, ""
    if delete_allowed_for_project(name):
        return True, ""
    stats = load_project_maturity(name)
    need_lines = min_lines_modified_for_delete()
    need_dev = min_dev_delegates_for_delete()
    return (
        False,
        (
            f"DELETE_MATURITY_GATE: 项目「{name}」累计修改 {stats.lines_modified_total}/{need_lines} 行、"
            f"开发委派 {stats.dev_delegate_runs}/{need_dev} 次，未达删除权限门槛"
        ),
    )


def record_lines_modified(project_name: str, delta_lines: int) -> None:
    if not project_name or delta_lines <= 0:
        return
    with _LOCK:
        stats = load_project_maturity(project_name)
        stats.lines_modified_total += int(delta_lines)
        save_project_maturity(project_name, stats)


def record_dev_delegate_run(project_name: str) -> None:
    if not project_name:
        return
    with _LOCK:
        stats = load_project_maturity(project_name)
        stats.dev_delegate_runs += 1
        save_project_maturity(project_name, stats)


def format_maturity_status_line(project_name: str) -> str:
    stats = load_project_maturity(project_name)
    ok = delete_allowed_for_project(project_name)
    flag = "可删" if ok else "禁删"
    return (
        f"  项目成熟度: 修改 {stats.lines_modified_total}/{min_lines_modified_for_delete()} 行 · "
        f"开发委派 {stats.dev_delegate_runs}/{min_dev_delegates_for_delete()} 次 · 删除 {flag}"
    )


__all__ = [
    "ProjectMaturityStats",
    "delete_allowed_for_path",
    "delete_allowed_for_project",
    "format_maturity_status_line",
    "load_project_maturity",
    "min_dev_delegates_for_delete",
    "min_lines_modified_for_delete",
    "project_delete_gate_enabled",
    "project_for_resolved_path",
    "record_dev_delegate_run",
    "record_lines_modified",
]
