"""Extension verify best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.registry.mcp_catalog_ops import load_json_file_safe


def dispatch_golden_tool_safe(
    tool_name: str,
    golden_args: dict[str, Any],
) -> tuple[bool, str | None, str | None]:
    """Return ``(ok, raw_result, error_detail)``."""
    try:
        from butler.mcp.registry_hook import dispatch_mcp_tool

        raw = dispatch_mcp_tool(tool_name, dict(golden_args))
    except Exception as exc:
        return False, None, str(exc)[:200]
    return True, str(raw), None


def read_verify_cache_dict_safe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    data = load_json_file_safe(path)
    return data if isinstance(data, dict) else {}
