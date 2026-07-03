"""MCP profile config load helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.registry.mcp_catalog_ops import load_yaml_dict_safe


def load_profile_config_dict_safe(path: Path) -> dict[str, Any] | None:
    return load_yaml_dict_safe(path)
