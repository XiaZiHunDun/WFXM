"""Path safety best-effort probes (P0-A)."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort


from butler.project.worktree import effective_workspace
from butler.project.manager import get_project_manager
from butler.execution_context import (
    get_current_session_key,
    get_audit_session_key,
    get_current_orchestrator,
)
from butler.core.tool_result_storage import is_readable_session_tool_result_path
from butler.permissions import check_external_path_override
from butler.tools.butlerignore import (
    is_butlerignored,
    is_protected_write_path,
)
from butler.config import get_butler_settings

def workspace_from_project_safe(project: object | None) -> Path | None:
    workspace = getattr(project, "workspace", None) if project is not None else None
    if not workspace:
        return None

    def _effective() -> Path:

        return effective_workspace(Path(workspace))

    result = safe_best_effort(
        _effective,
        label="path_safety.workspace_from_project",
        default=None,
    )
    if result is not None:
        return result
    try:
        return Path(workspace).expanduser().resolve(strict=False)
    except (OSError, ValueError, TypeError):
        return None


def workspace_for_session_key_safe(session_key: str) -> Path | None:
    sk = str(session_key or "").strip()
    if not sk:
        return None

    def _run() -> Path | None:

        pm = get_project_manager()
        return workspace_from_project_safe(pm.get_current(session_key=sk))

    return safe_best_effort(_run, label="path_safety.workspace_for_session", default=None)


def default_project_workspace_safe() -> Path | None:
    name = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip()
    if not name:
        return None

    def _run() -> Path | None:

        return workspace_from_project_safe(get_project_manager().get_project(name))

    return safe_best_effort(_run, label="path_safety.default_project_workspace", default=None)


def current_session_key_safe() -> str:
    def _run() -> str:

        return str(get_current_session_key() or "").strip()

    result = safe_best_effort(_run, label="path_safety.current_session_key", default="")
    return str(result or "")


def orchestrator_workspace_safe(session_key: str) -> Path | None:
    def _run() -> Path | None:
        orch = current_orchestrator_safe()
        if orch is None:
            return None
        manager = getattr(orch, "project_manager", None)
        project = (
            manager.get_current(session_key=session_key)
            if manager and hasattr(manager, "get_current")
            else None
        )
        return workspace_from_project_safe(project)

    return safe_best_effort(_run, label="path_safety.orchestrator_workspace", default=None)


def audit_session_key_safe(fallback: str = "") -> str:
    def _run() -> str:

        return str(get_audit_session_key(fallback=fallback) or "").strip()

    result = safe_best_effort(_run, label="path_safety.audit_session_key", default="")
    return str(result or "")


def is_readable_session_tool_result_path_safe(resolved: Path) -> bool:
    def _run() -> bool:

        return bool(is_readable_session_tool_result_path(str(resolved)))

    result = safe_best_effort(
        _run,
        label="path_safety.session_tool_result_path",
        default=False,
    )
    return bool(result)


def external_path_override_allowed_safe(resolved: Path, *, for_write: bool) -> bool | None:
    """Return True if override allows; False if denied; None if check unavailable."""

    def _run() -> bool:

        override = check_external_path_override(str(resolved), for_write=for_write)
        return bool(override is not None and override.allowed)

    return safe_best_effort(
        _run,
        label="path_safety.external_path_override",
        default=None,
    )


def butlerignore_blocked_safe(
    resolved: Path,
    *,
    workspace: Path,
    for_write: bool,
) -> str:
    """Return error message if blocked; empty string if allowed or check skipped."""

    def _run() -> str:

        if not for_write and is_butlerignored(resolved, workspace=workspace):
            return "Access denied: path matches .butlerignore"
        if for_write and is_protected_write_path(resolved, workspace=workspace):
            return "Access denied: protected path (sandbox policy)"
        return ""

    result = safe_best_effort(_run, label="path_safety.butlerignore", default="")
    return str(result or "")


def current_orchestrator_safe() -> Any | None:
    def _run() -> Any:

        return get_current_orchestrator()

    return safe_best_effort(_run, label="path_safety.current_orchestrator", default=None)


def configured_safe_root_safe() -> Path | None:
    raw = os.getenv("BUTLER_TOOL_SAFE_ROOT", "").strip()
    if not raw:
        return None

    def _run() -> Path:
        return Path(raw).expanduser().resolve()

    return safe_best_effort(_run, label="path_safety.configured_safe_root", default=None)


_HOOK_CONFIG_NAMES = frozenset({"hooks.yaml", "hooks.yml"})


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def hooks_global_dir_blocks_write(resolved: Path) -> bool:
    def _run() -> bool:

        global_dir = (
            get_butler_settings().butler_home / ".butler"
        ).resolve(strict=False)
        return _is_relative_to(resolved, global_dir) and resolved.name in _HOOK_CONFIG_NAMES

    result = safe_best_effort(_run, label="path_safety.hooks_global_dir", default=False)
    return bool(result)
