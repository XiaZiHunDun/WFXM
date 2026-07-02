"""Registry diagnostics for /诊断."""

from __future__ import annotations

from typing import Any

from butler.ops.registry_diagnostics_ops import (
    append_installed_skills_lines,
    append_mcp_catalog_line,
    append_mcp_lock_error_lines,
    append_registry_enabled_line,
    extend_mcp_merge_lines,
)


def format_registry_diagnostic_lines(
    health: dict[str, Any] | None = None,
    *,
    session_key: str = "",
) -> list[str]:
    lines: list[str] = []
    append_registry_enabled_line(lines)
    append_installed_skills_lines(lines)
    append_mcp_catalog_line(lines)
    extend_mcp_merge_lines(lines, session_key=session_key)
    append_mcp_lock_error_lines(lines)
    return lines
