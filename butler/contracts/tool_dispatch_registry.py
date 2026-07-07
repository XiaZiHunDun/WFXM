"""Runtime registration for ToolDispatchPort."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.tool_dispatch_ports import ToolDispatchPort

_LOCK = threading.RLock()
_TOOL_DISPATCH: ToolDispatchPort | None = None


def set_tool_dispatch(port: ToolDispatchPort | None) -> None:
    global _TOOL_DISPATCH
    with _LOCK:
        _TOOL_DISPATCH = port


def get_tool_dispatch() -> ToolDispatchPort | None:
    with _LOCK:
        return _TOOL_DISPATCH


__all__ = ["get_tool_dispatch", "set_tool_dispatch"]
