"""Resolve delegate_task category presets to role, prompt, and tool policy."""

from __future__ import annotations

from pathlib import Path
from typing import Any

_BUILTIN = Path(__file__).resolve().parent / "delegate_categories.yaml"


def _user_override_path() -> Path:
    import os

    return Path(os.path.expanduser("~/.butler/delegate_categories.yaml"))


def _load_yaml() -> dict[str, Any]:
    from butler.delegate.category_resolver_ops import load_delegate_categories_from_path_safe

    paths = [_user_override_path(), _BUILTIN]
    merged: dict[str, Any] = {}
    for path in paths:
        if not path.is_file():
            continue
        merged.update(load_delegate_categories_from_path_safe(path))
    return merged


def list_categories() -> list[str]:
    return sorted(_load_yaml().keys())


def resolve_category(category: str) -> dict[str, Any] | None:
    key = str(category or "").strip().lower()
    if not key:
        return None
    raw = _load_yaml().get(key)
    if not isinstance(raw, dict):
        return None
    return dict(raw)


def apply_category_to_delegate(
    *,
    category: str,
    role: str,
    task: str,
    context: str,
) -> tuple[str, str, str, dict[str, Any]]:
    """Return (role, task, context, meta) after category resolution."""
    preset = resolve_category(category)
    if preset is None:
        return role, task, context, {"category": category, "resolved": False}

    resolved_role = str(preset.get("role") or role or "dev").strip().lower()
    append = str(preset.get("prompt_append") or "").strip()
    new_task = task
    if append:
        new_task = f"{append}\n\n{task}".strip()

    meta: dict[str, Any] = {
        "category": category,
        "resolved": True,
        "description": preset.get("description", ""),
        "max_iterations": preset.get("max_iterations"),
        "allow_tools": preset.get("allow_tools"),
        "deny_tools": preset.get("deny_tools"),
        "background": preset.get("background"),
    }
    return resolved_role, new_task, context, meta
