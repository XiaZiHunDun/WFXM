"""Outbound preference best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def mark_slash_single_bubble_on_bridge_safe() -> bool:
    def _run() -> bool:
        from butler.execution_context import get_current_turn_bridge

        bridge = get_current_turn_bridge()
        if bridge is not None:
            bridge.slash_single_bubble = True
            return True
        return False

    result = safe_best_effort(
        _run,
        label="outbound_prefs.slash_single_bubble",
        default=False,
    )
    return bool(result)
