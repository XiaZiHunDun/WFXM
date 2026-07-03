"""Delegate policy best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def effective_delegate_max_iterations_safe(base: int) -> int:
    def _run() -> int:
        from butler.ops.eval_config_overrides import effective_delegate_max_iterations

        return int(effective_delegate_max_iterations(base))

    result = safe_best_effort(
        _run,
        label="delegate_policy.max_iterations",
        default=base,
    )
    return int(result) if isinstance(result, int) else base
