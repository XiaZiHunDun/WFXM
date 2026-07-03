"""Skill injection policy best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def is_session_read_recall_intent_safe(query: str) -> bool | None:
    """Return intent bool, or ``None`` when the check path failed."""

    def _run() -> bool:
        from butler.core.session_recall_intent import is_session_read_recall_intent

        return bool(is_session_read_recall_intent(query))

    result = safe_best_effort(
        _run,
        label="injection_policy.session_read_recall",
        default=None,
    )
    return bool(result) if isinstance(result, bool) else None


def record_skill_injection_metrics_safe(decision: Any) -> None:
    def _run() -> None:
        from butler.ops.runtime_metrics import inc

        if decision.skip and decision.reason == "experience_hit_skip_unverified_skill":
            inc("execution_fallback_skip")
        if decision.skill_names:
            inc("execution_ref_only_load", labels={"reason": decision.reason})

    safe_best_effort(_run, label="injection_policy.metrics", default=None)
