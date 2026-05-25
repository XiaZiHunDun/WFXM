"""OpenHands-style confirmation flags (主线 M)."""

from __future__ import annotations

from butler.env_parse import env_truthy


def two_phase_confirm_enabled() -> bool:
    return env_truthy("BUTLER_TWO_PHASE_CONFIRM", default=False)


def permission_risk_heuristic_enabled() -> bool:
    return env_truthy("BUTLER_PERMISSION_RISK_HEURISTIC", default=False)


def output_schema_repair_enabled() -> bool:
    return env_truthy("BUTLER_OUTPUT_SCHEMA_REPAIR", default=True)


__all__ = [
    "output_schema_repair_enabled",
    "permission_risk_heuristic_enabled",
    "two_phase_confirm_enabled",
]
