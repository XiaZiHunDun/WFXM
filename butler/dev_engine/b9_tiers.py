"""B9 LIVE task tiers — Tier-1 gate vs Tier-2 stretch goals."""

from __future__ import annotations

import os
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
    "B9L_prod_task_6d5304648da4",
    "B9L_prod_main_helpers_import",
    "B9L_prod_cross_module_rename",
    "B9L_prod_lingwen_demo_add",
    "B9L_prod_lingwen_workflow_guard",
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


def tier2_probe_gate_enabled() -> bool:
    raw = os.getenv("BUTLER_B9_TIER2_GATE_ENABLED", "1").strip().lower()
    return raw in ("1", "true", "yes", "on")


def tier2_probe_gate_min_passed() -> int:
    try:
        return max(0, int(os.getenv("BUTLER_B9_TIER2_GATE_MIN_PASSED", "2")))
    except ValueError:
        return 2


def evaluate_tier2_probe_gate(*, passed: int, total: int) -> dict[str, Any]:
    """Conditional weekly gate for B9_TUNING_PROBE_TASK_IDS (default 2/3)."""
    enabled = tier2_probe_gate_enabled()
    min_passed = tier2_probe_gate_min_passed()
    ok = (not enabled) or (int(passed) >= min_passed)
    return {
        "enabled": enabled,
        "min_passed": min_passed,
        "passed": int(passed),
        "total": int(total),
        "ok": ok,
    }


__all__ = [
    "B9_STUCK_TASK_IDS",
    "B9_TIER2_TASK_IDS",
    "b9_task_tier",
    "evaluate_tier2_probe_gate",
    "filter_tier_tasks",
    "summarize_tier_results",
    "tier2_probe_gate_enabled",
    "tier2_probe_gate_min_passed",
]
