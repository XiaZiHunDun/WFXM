"""Coding knowledge B9 retrieval best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def infer_b9_task_id_safe(text: str) -> str:
    def _run() -> str:
        from butler.dev_engine.prod_delegate_bridge import infer_b9_task_id

        return str(infer_b9_task_id(text) or "")

    result = safe_best_effort(
        _run,
        label="coding_knowledge.infer_b9_task",
        default="",
    )
    return str(result or "")


def experience_retrieval_eligible_safe(
    *,
    experience_id: str,
    normalized_keywords: set[str],
    inferred_task_id: str,
    benchmarks: dict[str, Any],
) -> bool:
    def _run() -> bool:
        from butler.dev_engine.b9_experience_retrieval import experience_retrieval_eligible

        return bool(
            experience_retrieval_eligible(
                experience_id,
                normalized_keywords=normalized_keywords,
                inferred_task_id=inferred_task_id,
                benchmarks=benchmarks,
            )
        )

    result = safe_best_effort(
        _run,
        label="coding_knowledge.retrieval_eligible",
        default=True,
    )
    return bool(result)


def experience_retrieval_rank_bonus_safe(
    *,
    experience_id: str,
    normalized_keywords: set[str],
    inferred_task_id: str,
    project_id: str,
    benchmarks: dict[str, Any],
    scope_level: str,
    scope_project_id: str,
    scope_source: str,
    domain: list[str],
) -> int:
    def _run() -> int:
        from butler.dev_engine.b9_experience_retrieval import experience_retrieval_rank_bonus

        return int(
            experience_retrieval_rank_bonus(
                experience_id=experience_id,
                normalized_keywords=normalized_keywords,
                inferred_task_id=inferred_task_id,
                project_id=project_id,
                benchmarks=benchmarks,
                scope_level=scope_level,
                scope_project_id=scope_project_id,
                scope_source=scope_source,
                domain=domain,
            )
        )

    result = safe_best_effort(
        _run,
        label="coding_knowledge.retrieval_rank_bonus",
        default=0,
    )
    return int(result or 0)
