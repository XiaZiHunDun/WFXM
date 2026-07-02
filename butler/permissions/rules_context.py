"""Workspace/session resolution and YAML loaders for permission rules (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from butler.core.best_effort import safe_best_effort


def load_permissions_yaml(workspace: Path | None) -> dict[str, Any]:
    if workspace is None:
        return {}

    def _from_file(path: Path) -> dict[str, Any] | None:
        if not path.is_file():
            return None
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}

    for rel in (".butler/permissions.yaml", ".butler/permissions.yml"):
        loaded = safe_best_effort(
            lambda rel=rel: _from_file(workspace / rel),
            label="permissions.rules_yaml",
            default=None,
        )
        if isinstance(loaded, dict) and loaded:
            return loaded
        if loaded == {}:
            return {}

    def _from_project_yaml() -> dict[str, Any]:
        proj = workspace / "project.yaml"
        if not proj.is_file():
            return {}
        data = yaml.safe_load(proj.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        perms = data.get("permissions")
        return perms if isinstance(perms, dict) else {}

    result = safe_best_effort(
        _from_project_yaml,
        label="permissions.project_yaml",
        default={},
    )
    return result if isinstance(result, dict) else {}


def security_blacklist_enabled() -> bool:
    def _run() -> bool:
        from butler.env_parse import env_truthy

        return env_truthy("BUTLER_PERMISSIONS_PARAM_BLACKLIST", default=True)

    result = safe_best_effort(
        _run,
        label="permissions.security_blacklist_flag",
        default=True,
    )
    return True if result is None else bool(result)


def is_session_tool_result_readable(path_str: str) -> bool:
    def _run() -> bool:
        from butler.core.tool_result_storage import is_readable_session_tool_result_path

        return bool(is_readable_session_tool_result_path(path_str))

    result = safe_best_effort(
        _run,
        label="permissions.session_tool_result_path",
        default=False,
    )
    return bool(result)


def current_workspace() -> Path | None:
    def _from_orchestrator() -> Path | None:
        from butler.execution_context import get_current_orchestrator, get_current_session_key

        orch = get_current_orchestrator()
        if orch is None:
            return None
        pm = getattr(orch, "project_manager", None)
        if pm is None:
            return None
        proj = pm.get_current(session_key=str(get_current_session_key() or ""))
        if proj is None:
            return None
        return Path(proj.workspace)

    ws = safe_best_effort(
        _from_orchestrator,
        label="permissions.workspace_orchestrator",
        default=None,
    )
    if ws is not None:
        return ws

    def _from_env() -> Path | None:
        import os

        raw = os.getenv("BUTLER_TOOL_SAFE_ROOT", "").strip()
        if not raw:
            return None
        p = Path(raw).expanduser()
        return p.resolve() if p.is_dir() else None

    return safe_best_effort(
        _from_env,
        label="permissions.workspace_env",
        default=None,
    )


def current_session_key() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    return safe_best_effort(
        _run,
        label="permissions.session_key",
        default="",
    ) or ""


def permission_request_hook_block(
    tool_name: str,
    args: dict[str, Any],
    *,
    reason: str,
    session_key: str,
) -> str | None:
    def _run() -> str | None:
        from butler.hooks.runner import run_permission_request_hooks

        return run_permission_request_hooks(
            tool_name,
            args,
            reason=reason,
            session_key=session_key,
        )

    return safe_best_effort(
        _run,
        label="permissions.request_hooks",
        default=None,
    )


__all__ = [
    "current_session_key",
    "current_workspace",
    "is_session_tool_result_readable",
    "load_permissions_yaml",
    "permission_request_hook_block",
    "security_blacklist_enabled",
]
