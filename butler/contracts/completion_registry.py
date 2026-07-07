"""Runtime registration for OutboundCompletionHooks."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.completion_ports import OutboundCompletionHooks

_LOCK = threading.RLock()
_COMPLETION_HOOKS: OutboundCompletionHooks | None = None


def set_completion_hooks(hooks: OutboundCompletionHooks | None) -> None:
    global _COMPLETION_HOOKS
    with _LOCK:
        _COMPLETION_HOOKS = hooks


def get_completion_hooks() -> OutboundCompletionHooks | None:
    with _LOCK:
        return _COMPLETION_HOOKS


__all__ = ["get_completion_hooks", "set_completion_hooks"]
