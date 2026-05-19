"""Thread-local parent LoopCallbacks for nested delegate_task runs."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from butler.core.agent_loop import LoopCallbacks

_local = threading.local()


def set_parent_callbacks(callbacks: Optional["LoopCallbacks"]) -> None:
    _local.callbacks = callbacks


def get_parent_callbacks() -> Optional["LoopCallbacks"]:
    return getattr(_local, "callbacks", None)


def child_callbacks(parent: Optional["LoopCallbacks"]) -> Optional["LoopCallbacks"]:
    """Subset of callbacks safe for nested agent loops."""
    if parent is None:
        return None
    from butler.core.agent_loop import LoopCallbacks
    return LoopCallbacks(
        on_tool_start=parent.on_tool_start,
        on_tool_complete=parent.on_tool_complete,
        on_error=parent.on_error,
    )
