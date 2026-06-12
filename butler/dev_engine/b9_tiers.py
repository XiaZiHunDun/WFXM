"""B9 LIVE task tiers — Tier-1 gate vs Tier-2 stretch goals."""

from __future__ import annotations

from typing import Any

# Stretch: import/cross-file/prod-shaped wrong_patch probes.
B9_TIER2_TASK_IDS: frozenset[str] = frozenset({
    "B9L_multi_file_import",
    "B9L_pytest_fix_impl",
    "B9L_cross_module_rename",
    "B9L_prod_verify_fail",
    "B9L_prod_patch_wrong",
    "B9L_prod_demo_fix_greet_return",
    "B9L_prod_read_state_greet",
    "B9L_prod_main_helpers_import",
})

# STUCK expects verify to fail (agent should not fix); excluded from Tier-1 pass_rate.
B9_STUCK_TASK_IDS: frozenset[str] = frozenset({"B9L_stuck_unsolvable"})


def b9_task_tier(task_id: str) -> int:
    return 2 if task_id in B9_TIER2_TASK_IDS else 1


def filter_tier_tasks(
    tasks: list[Any],
    *,
    tier: int,
) -> list[Any]:
    return [t for t in tasks if b9_task_tier(getattr(t, "task_id", "")) == tier]


def summarize_tier_results(results: list[dict[str, Any]]) -> dict[str, Any]:
    """Summarize pass rates for tier1/tier2 (excludes stuck from solvable)."""
    tiers: dict[str, dict[str, Any]] = {}
    for tier_n in (1, 2):
        tier_key = f"tier{tier_n}"
        rows = [r for r in results if b9_task_tier(str(r.get("task_id") or "")) == tier_n]
        solvable = [r for r in rows if r.get("task_id") not in B9_STUCK_TASK_IDS]
        passed = sum(1 for r in solvable if r.get("passed"))
        total = len(solvable)
        tiers[tier_key] = {
            "passed": passed,
            "total": total,
            "pass_rate": round(passed / total, 4) if total else 0.0,
            "task_ids": [r.get("task_id") for r in rows],
        }
    return tiers


__all__ = [
    "B9_STUCK_TASK_IDS",
    "B9_TIER2_TASK_IDS",
    "b9_task_tier",
    "filter_tier_tasks",
    "summarize_tier_results",
]
