"""Shared environment variable parsing for Butler."""

from __future__ import annotations

import os


def env_truthy(name: str, *, default: bool = False) -> bool:
    """Return True when ``name`` is set to 1/true/yes/on (case-insensitive)."""
    raw = os.getenv(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")
