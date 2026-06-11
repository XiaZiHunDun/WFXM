"""Normalize and validate LLM tool args before dispatch."""

from __future__ import annotations

from typing import Any

_PATH_TOOLS = frozenset({"read_file", "write_file", "patch", "delete_file"})
_PATH_ALIASES = ("file", "file_path", "filepath", "filename")

_TOOL_REQUIRED: dict[str, tuple[str, ...]] = {
    "read_file": ("path",),
    "write_file": ("path", "content"),
    "patch": ("path", "old_string", "new_string"),
    "delete_file": ("path",),
    "terminal": ("command",),
}

# Keys that must be present and non-blank strings (empty new_string is allowed for patch).
_NON_EMPTY_STRING: dict[str, frozenset[str]] = {
    "read_file": frozenset({"path"}),
    "write_file": frozenset({"path"}),
    "patch": frozenset({"path", "old_string"}),
    "delete_file": frozenset({"path"}),
    "terminal": frozenset({"command"}),
}

_TOOL_HINTS: dict[str, str] = {
    "patch": "patch requires: path, old_string (exact match), new_string (may be empty to delete).",
    "write_file": "write_file requires: path, content.",
    "read_file": "read_file requires: path.",
    "delete_file": "delete_file requires: path.",
    "terminal": "terminal requires: command.",
}


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


def _missing_required_fields(name: str, args: dict[str, Any]) -> list[str]:
    required = _TOOL_REQUIRED.get(name)
    if not required:
        return []
    non_empty = _NON_EMPTY_STRING.get(name, frozenset())
    missing: list[str] = []
    for field in required:
        if field not in args:
            missing.append(field)
            continue
        val = args[field]
        if val is None:
            missing.append(field)
            continue
        if field in non_empty and isinstance(val, str) and not val.strip():
            missing.append(field)
    return missing


def validate_tool_args(name: str, args: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a structured error payload when required args are missing; else None."""
    missing = _missing_required_fields(name, dict(args or {}))
    if not missing:
        return None
    hint = _TOOL_HINTS.get(name, f"{name} missing: {', '.join(missing)}")
    return {
        "error": f"{name} missing required arguments: {', '.join(missing)}",
        "code": "TOOL_ARGS_INVALID",
        "tool": name,
        "missing": missing,
        "hint": hint,
    }


__all__ = ["normalize_tool_args", "validate_tool_args"]
