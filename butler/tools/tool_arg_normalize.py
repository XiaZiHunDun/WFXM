"""Normalize common LLM tool-arg aliases before dispatch."""

from __future__ import annotations

from typing import Any

_PATH_TOOLS = frozenset({"read_file", "write_file", "patch", "delete_file"})
_PATH_ALIASES = ("file", "file_path", "filepath", "filename")


def normalize_tool_args(name: str, args: dict[str, Any] | None) -> dict[str, Any]:
    """Coerce alternate keys (e.g. ``file`` → ``path``) for path-scoped tools."""
    out = dict(args or {})
    if name not in _PATH_TOOLS or out.get("path"):
        return out
    for alt in _PATH_ALIASES:
        val = out.get(alt)
        if val:
            out["path"] = val
            break
    return out


__all__ = ["normalize_tool_args"]
