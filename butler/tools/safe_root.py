"""Tool workspace root — shim over path_safety.tool_safe_root."""

from __future__ import annotations

from pathlib import Path

from butler.tools.path_safety import tool_safe_root


def get_tool_safe_root() -> Path:
    """Return the active directory tools may read/write (project workspace or BUTLER_TOOL_SAFE_ROOT)."""
    return tool_safe_root()


__all__ = ["get_tool_safe_root"]
