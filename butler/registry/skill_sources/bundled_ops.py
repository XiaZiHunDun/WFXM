"""Bundled skill index load helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from butler.registry.mcp_catalog_ops import load_yaml_dict_safe


def load_bundled_index_safe(path: Path) -> dict[str, Any] | None:
    return cast(dict[str, Any] | None, load_yaml_dict_safe(path))
