"""Tool filesystem scope — environment (safe root) vs project workspace jail."""

from __future__ import annotations

import os
from pathlib import Path

from butler.config import get_butler_settings
from butler.project.policy_env import bind_default_project_enabled


def environment_tool_scope_enabled() -> bool:
    """When true, tools use BUTLER_TOOL_SAFE_ROOT (or repo root), not project workspace jail."""
    raw = (os.getenv("BUTLER_TOOL_SCOPE", "environment") or "environment").strip().lower()
    if raw in ("project", "workspace", "0", "false", "off"):
        return False
    return True


def resolve_environment_tool_root() -> Path:
    from butler.tools.path_safety_ops import configured_safe_root_safe

    configured = configured_safe_root_safe()
    if configured is not None:
        return configured
    settings = get_butler_settings()
    return settings.projects_dir.expanduser().resolve().parent


def workspace_anchor_strict_for_paths() -> bool:
    """Relative paths anchor to project workspace only in legacy project scope + strict flag."""
    if environment_tool_scope_enabled():
        return False
    return os.getenv("BUTLER_WORKSPACE_ANCHOR_STRICT", "1").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def project_relative_path_anchors_to_workspace() -> bool:
    """When a project is active, relative paths resolve under its workspace (even in environment scope)."""
    if not environment_tool_scope_enabled():
        return workspace_anchor_strict_for_paths()
    raw = (os.getenv("BUTLER_TOOL_PROJECT_ANCHOR", "1") or "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


__all__ = [
    "bind_default_project_enabled",
    "environment_tool_scope_enabled",
    "project_relative_path_anchors_to_workspace",
    "resolve_environment_tool_root",
    "workspace_anchor_strict_for_paths",
]
