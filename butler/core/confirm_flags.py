"""OpenHands-style confirmation flags (主线 M)."""

from __future__ import annotations

from butler.defaults.env_defaults import OUTPUT_SCHEMA_REPAIR_MAX
from butler.env_parse import env_truthy


def two_phase_confirm_enabled() -> bool:
    return env_truthy("BUTLER_TWO_PHASE_CONFIRM", default=False)


def permission_risk_heuristic_enabled() -> bool:
    return env_truthy("BUTLER_PERMISSION_RISK_HEURISTIC", default=False)


def output_schema_repair_enabled() -> bool:
    return env_truthy("BUTLER_OUTPUT_SCHEMA_REPAIR", default=True)


def output_schema_repair_max_rounds() -> int:
    import os

    try:
        raw = os.getenv("BUTLER_OUTPUT_SCHEMA_REPAIR_MAX", str(OUTPUT_SCHEMA_REPAIR_MAX))
        return max(1, min(3, int(raw)))
    except ValueError:
        return OUTPUT_SCHEMA_REPAIR_MAX


__all__ = [
    "output_schema_repair_enabled",
    "output_schema_repair_max_rounds",
    "permission_risk_heuristic_enabled",
    "two_phase_confirm_enabled",
]
