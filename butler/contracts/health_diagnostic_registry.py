"""Runtime registration for HealthDiagnosticPort."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.health_diagnostic_ports import HealthDiagnosticPort

_LOCK = threading.RLock()
_HEALTH_DIAGNOSTIC: HealthDiagnosticPort | None = None


def set_health_diagnostic(port: HealthDiagnosticPort | None) -> None:
    global _HEALTH_DIAGNOSTIC
    with _LOCK:
        _HEALTH_DIAGNOSTIC = port


def get_health_diagnostic() -> HealthDiagnosticPort | None:
    with _LOCK:
        return _HEALTH_DIAGNOSTIC


__all__ = ["get_health_diagnostic", "set_health_diagnostic"]
