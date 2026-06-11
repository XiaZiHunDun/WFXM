"""Delegation safety policy (from Hermes delegate_tool)."""

from __future__ import annotations

from butler.env_parse import env_truthy, int_env

DELEGATE_BLOCKED_TOOLS = frozenset({
    "delegate_task",
    "run_workflow",
})

MAX_DELEGATE_DEPTH = 2


def delegate_one_tool_per_iteration() -> bool:
    """Manus-style single tool call per delegate iteration (default off — slower reads)."""
    return env_truthy("BUTLER_DELEGATE_ONE_TOOL_PER_ITERATION", default=False)


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
        base = int_env("BUTLER_DELEGATE_MAX_ITERATIONS", 24, min=1, max=200)
    except ValueError:
        base = 24
    try:
        from butler.ops.eval_config_overrides import effective_delegate_max_iterations

        return effective_delegate_max_iterations(base)
    except Exception:
        return base
