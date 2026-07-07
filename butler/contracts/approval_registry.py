"""Runtime registration for ApprovalStore."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.approval_ports import ApprovalStore

_LOCK = threading.RLock()
_APPROVAL_STORE: ApprovalStore | None = None


def set_approval_store(store: ApprovalStore | None) -> None:
    global _APPROVAL_STORE
    with _LOCK:
        _APPROVAL_STORE = store


def get_approval_store() -> ApprovalStore | None:
    with _LOCK:
        return _APPROVAL_STORE


__all__ = ["get_approval_store", "set_approval_store"]
