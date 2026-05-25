"""Shallow merge of ``project.yaml`` ``plugins:`` into process env (env wins)."""

from __future__ import annotations

import os
from typing import Any

from butler.project import Project


def _normalize_plugins(raw: Any) -> dict[str, str]:
    if not raw:
        return {}
    if isinstance(raw, dict):
        out: dict[str, str] = {}
        for key, val in raw.items():
            k = str(key or "").strip()
            if not k.startswith("BUTLER_"):
                continue
            out[k] = str(val if val is not None else "").strip()
        return out
    if isinstance(raw, list):
        out = {}
        for item in raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or item.get("env") or "").strip()
            if not name.startswith("BUTLER_"):
                continue
            if item.get("enabled") is False:
                continue
            val = item.get("value")
            if val is None:
                val = "1"
            out[name] = str(val).strip()
        return out
    return {}


def plugins_from_project(project: Project | None) -> dict[str, str]:
    if project is None:
        return {}
    return _normalize_plugins(getattr(project, "plugins", None))


def apply_project_plugins(project: Project | None) -> dict[str, str]:
    """Apply yaml plugin env keys only when not already set in os.environ."""
    applied: dict[str, str] = {}
    for key, value in plugins_from_project(project).items():
        if key in os.environ:
            continue
        os.environ[key] = value
        applied[key] = value
    return applied


normalize_plugins = _normalize_plugins

__all__ = [
    "apply_project_plugins",
    "normalize_plugins",
    "plugins_from_project",
]
