"""Runtime turn memory scoring best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def score_memory_effectiveness_for_session_safe(session_id: str) -> Any | None:
    def _run() -> Any:
        from butler.memory.memory_metrics import get_collector
        from butler.ops.eval_scoring import score_memory_effectiveness

        metrics = get_collector().get_session_metrics(session_id)
        computed = metrics.get("computed", {}) if isinstance(metrics, dict) else {}
        return score_memory_effectiveness(
            write_survival_rate=float(computed.get("write_survival_rate", 0.0) or 0.0),
            first_turn_hit_rate=float(computed.get("first_turn_hit_rate", 0.0) or 0.0),
            decay_error_rate=float(computed.get("decay_error_rate", 0.0) or 0.0),
        )

    return safe_best_effort(
        _run,
        label="eval_turn.memory_score",
        default=None,
    )
