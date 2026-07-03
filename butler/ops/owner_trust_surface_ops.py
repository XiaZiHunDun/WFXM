"""Owner trust surface best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def boundary_warn_count_safe() -> int:
    def _run() -> int:
        from butler.ops.boundary_observability import collect_boundary_observations

        return sum(
            1 for obs in collect_boundary_observations() if obs.status == "warn"
        )

    result = safe_best_effort(
        _run,
        label="owner_trust.boundary_warns",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0


def execution_trust_session_safe(session_key: str) -> dict[str, int]:
    sk = str(session_key or "").strip()

    def _run() -> dict[str, int]:
        from butler.ops.execution_surface_diagnostics import collect_execution_trust_metrics

        metrics = collect_execution_trust_metrics(session_key=sk)
        sess = metrics.get("session")
        if isinstance(sess, dict):
            return {str(k): int(v) for k, v in sess.items()}
        return {}

    result = safe_best_effort(
        _run,
        label="owner_trust.execution_trust",
        default={},
    )
    return result if isinstance(result, dict) else {}


def skill_injection_mode_safe() -> str | None:
    def _run() -> str:
        from butler.skills.injection_policy import skill_injection_mode

        return str(skill_injection_mode())

    result = safe_best_effort(
        _run,
        label="owner_trust.skill_mode",
        default=None,
    )
    return str(result) if result else None


def approval_stats_for_health_safe(session_key: str) -> dict[str, Any]:
    sk = str(session_key or "").strip()

    def _run() -> dict[str, Any]:
        from butler.ops.health_report import collect_approval_stats_for_health

        stats = collect_approval_stats_for_health(sk)
        return dict(stats) if isinstance(stats, dict) else {}

    result = safe_best_effort(
        _run,
        label="owner_trust.approval_stats",
        default={},
    )
    return result if isinstance(result, dict) else {}


def memory_sources_line_safe(health: dict[str, Any]) -> str:
    h = dict(health or {})

    def _run() -> str:
        from butler.core.memory_source_surface import format_memory_sources_one_liner

        return str(format_memory_sources_one_liner(h))

    result = safe_best_effort(
        _run,
        label="owner_trust.memory_line",
        default="",
    )
    return str(result or "")
