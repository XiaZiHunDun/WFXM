"""Project preflight best-effort helpers (P0-A)."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import yaml  # type: ignore[import-untyped]

from butler.core.best_effort import safe_best_effort
from butler.project.model import Project

logger = logging.getLogger(__name__)


def try_load_project_yaml(config: Path) -> tuple[Project | None, str | None]:
    try:
        return Project.from_yaml(config), None
    except Exception as exc:
        return None, str(exc)


def detect_lifecycle_tag(workspace: Path) -> str:
    state = workspace / "novel-factory" / "workflow_state.json"
    if not state.is_file():
        return ""
    try:
        data = yaml.safe_load(state.read_text(encoding="utf-8")) or {}
    except Exception:
        try:
            data = json.loads(state.read_text(encoding="utf-8"))
        except Exception:
            return ""
    phase = str(data.get("phase") or data.get("current_phase") or "").upper()
    if "COMPLETE" in phase:
        return "lifecycle:complete"
    return "lifecycle:active"


def probe_project_registration_safe(
    project_name: str,
    *,
    cfg_is_file: bool,
) -> tuple[bool, bool, bool]:
    """Return (registered, ok_item, warn_not_registered). Skipped → (False, False, False)."""

    def _run() -> tuple[bool, bool, bool]:
        from butler.project.manager import get_project_manager

        pm = get_project_manager()
        if project_name and pm.get_project(project_name) is not None:
            return True, True, False
        if cfg_is_file and project_name:
            return False, False, True
        return False, False, False

    result = safe_best_effort(
        _run,
        label="preflight.project_registration",
        default=(False, False, False),
    )
    if isinstance(result, tuple) and len(result) == 3:
        return result
    return False, False, False


def project_skills_sync_issues_safe(workspace: Path) -> list[str]:
    def _run() -> list[str]:
        from butler.ops.execution_surface_diagnostics import project_skills_sync_issues

        return list(project_skills_sync_issues(workspace) or [])

    result = safe_best_effort(
        _run,
        label="preflight.skills_sync",
        default=[],
    )
    return result if isinstance(result, list) else []
