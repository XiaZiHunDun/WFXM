"""Task route hint best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def cc_bridge_enabled_for_hints_safe() -> bool:
    def _run() -> bool:
        from butler.runtime.cc_bridge import cc_bridge_enabled

        return bool(cc_bridge_enabled())

    result = safe_best_effort(
        _run,
        label="task_route_hints.cc_bridge_enabled",
        default=False,
    )
    return bool(result)
