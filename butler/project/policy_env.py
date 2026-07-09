"""Project policy env flags (no manager/path_safety imports — cycle-safe)."""

from __future__ import annotations

from butler.env_parse import env_truthy


def bind_default_project_enabled() -> bool:
    """When false (default), gateway/CLI start as personal butler without auto /切换."""
    return bool(env_truthy("BUTLER_BIND_DEFAULT_PROJECT", default=False))


__all__ = ["bind_default_project_enabled"]
