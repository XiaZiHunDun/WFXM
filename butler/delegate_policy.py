"""Delegation safety policy (from Hermes delegate_tool)."""

from __future__ import annotations

import os

DELEGATE_BLOCKED_TOOLS = frozenset({
    "delegate_task",
    "run_workflow",
})

MAX_DELEGATE_DEPTH = 2


def resolve_delegate_max_iterations(category_meta: dict | None = None) -> int:
    """Independent iteration cap for child delegate loops (Hermes IterationBudget subset)."""
    meta = category_meta if isinstance(category_meta, dict) else {}
    raw = meta.get("max_iterations")
    if raw is not None:
        try:
            return max(1, min(200, int(raw)))
        except (TypeError, ValueError):
            pass
    try:
        return max(1, min(200, int(os.getenv("BUTLER_DELEGATE_MAX_ITERATIONS", "24"))))
    except ValueError:
        return 24
