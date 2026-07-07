"""Runtime registration for ToolRegistryReadPort."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.tool_registry_ports import ToolRegistryReadPort

_LOCK = threading.RLock()
_TOOL_REGISTRY_READ: ToolRegistryReadPort | None = None


def set_tool_registry_read(port: ToolRegistryReadPort | None) -> None:
    global _TOOL_REGISTRY_READ
    with _LOCK:
        _TOOL_REGISTRY_READ = port


def get_tool_registry_read() -> ToolRegistryReadPort | None:
    with _LOCK:
        return _TOOL_REGISTRY_READ


__all__ = ["get_tool_registry_read", "set_tool_registry_read"]
