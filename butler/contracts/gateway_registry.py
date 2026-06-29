"""Runtime registration for OwnerGate + BridgeAccess (gateway wires at startup)."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.bridge_access import BridgeAccess
    from butler.contracts.owner_gate import OwnerGate

_LOCK = threading.RLock()
_OWNER_GATE: OwnerGate | None = None
_BRIDGE_ACCESS: BridgeAccess | None = None


def set_owner_gate(gate: OwnerGate | None) -> None:
    global _OWNER_GATE
    with _LOCK:
        _OWNER_GATE = gate


def get_owner_gate() -> OwnerGate | None:
    with _LOCK:
        return _OWNER_GATE


def set_bridge_access(access: BridgeAccess | None) -> None:
    global _BRIDGE_ACCESS
    with _LOCK:
        _BRIDGE_ACCESS = access


def get_bridge_access() -> BridgeAccess | None:
    with _LOCK:
        return _BRIDGE_ACCESS


__all__ = [
    "get_bridge_access",
    "get_owner_gate",
    "set_bridge_access",
    "set_owner_gate",
]
