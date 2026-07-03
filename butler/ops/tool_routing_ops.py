"""Eval tool routing hint best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def delegate_routing_hint_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.ops.eval_config_overrides import delegate_routing_hint_enabled

        return bool(delegate_routing_hint_enabled())

    result = safe_best_effort(
        _run,
        label="tool_routing.delegate_hint_enabled",
        default=False,
    )
    return bool(result)
