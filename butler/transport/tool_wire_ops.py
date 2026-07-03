"""Tool wire conversion best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def convert_provider_tools_safe(transport: Any, tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        converted = transport.convert_tools(tools)
        return list(converted or tools)

    result = safe_best_effort(
        _run,
        label="tool_wire.convert_tools",
        default=tools,
    )
    return list(result) if isinstance(result, list) else tools
