"""Completion push env policy — shared by outbound_bridge and completion_notify (no cross-import)."""

from __future__ import annotations

from typing import cast

from butler.defaults.env_defaults import GATEWAY_MAX_SUPPLEMENTARY_PER_TURN
from butler.env_parse import env_truthy, int_env


def suppress_completion_after_main_enabled() -> bool:
    return cast(bool, env_truthy("BUTLER_GATEWAY_SUPPRESS_COMPLETION_AFTER_MAIN", default=True))


def max_supplementary_per_turn() -> int:
    return cast(
        int,
        int_env(
            "BUTLER_GATEWAY_MAX_SUPPLEMENTARY_PER_TURN",
            GATEWAY_MAX_SUPPLEMENTARY_PER_TURN,
            min=0,
        ),
    )


__all__ = ["max_supplementary_per_turn", "suppress_completion_after_main_enabled"]
