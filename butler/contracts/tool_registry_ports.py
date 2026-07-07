"""Read-only tool registry Protocol — tool_audit without importing registry."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class ToolRegistryReadPort(Protocol):
    """Check whether a tool name is registered (audit error classification)."""

    def is_tool_registered(self, name: str) -> bool: ...


__all__ = ["ToolRegistryReadPort"]
