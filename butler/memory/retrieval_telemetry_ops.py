"""Best-effort degradation sync for retrieval telemetry (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def sync_recall_degradation_safe(*, recall_degraded: bool) -> None:
    if recall_degraded:

        def _register() -> None:
            from butler.ops.degradation_registry import register_degradation

            register_degradation("recall", "hybrid 异常，仅 FTS")

        safe_best_effort(
            _register,
            label="retrieval_telemetry.degradation_register",
            default=None,
        )
    else:

        def _clear() -> None:
            from butler.ops.degradation_registry import clear_degradation

            clear_degradation("recall")

        safe_best_effort(
            _clear,
            label="retrieval_telemetry.degradation_clear",
            default=None,
        )
