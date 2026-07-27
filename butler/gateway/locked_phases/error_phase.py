from __future__ import annotations

from typing import Optional, cast

from butler.gateway.locked_phases_ops import format_gateway_error_card


def _phase_format_error_card(exc: BaseException, turn_elapsed: float) -> Optional[str]:
    return cast(
        Optional[str],
        format_gateway_error_card(exc, turn_elapsed),
    )