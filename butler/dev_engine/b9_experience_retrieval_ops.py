"""B9 experience retrieval best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def experience_task_affinity_safe(experience_id: str, *, inferred_task_id: str) -> bool:
    def _run() -> bool:
        from butler.dev_engine.prod_delegate_bridge import experience_task_affinity

        return bool(experience_task_affinity(experience_id, inferred_task_id=inferred_task_id))

    result = safe_best_effort(
        _run,
        label="b9_experience_retrieval.task_affinity",
        default=False,
    )
    return bool(result)
