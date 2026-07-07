"""Review closure best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.review_ports import DevReviewView
from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def reflection_closure_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.core.reflection_closure import reflection_closure_enabled

        return bool(reflection_closure_enabled())

    result = safe_best_effort(_run, label="review_closure.reflection_enabled", default=False)
    return bool(result)


def closure_write_flags_safe() -> bool:
    def _run() -> bool:
        from butler.env_parse import env_truthy

        return bool(
            env_truthy("BUTLER_REFLECTION_CLOSURE_WRITE", default=False)
            or env_truthy("BUTLER_REFLEXION_WRITE_EXPERIENCE", default=False)
        )

    result = safe_best_effort(_run, label="review_closure.write_flags", default=False)
    return bool(result)


def persist_reflect_closure_safe(
    *,
    cause: str,
    session_key: str,
    source: str,
    findings_count: int,
) -> None:
    def _run() -> None:
        from butler.core.reflection_closure import maybe_persist_reflect_closure

        maybe_persist_reflect_closure(
            trigger="review_fail",
            cause=cause,
            strategy="address_review_findings",
            detail=f"findings={findings_count}",
            session_key=session_key,
            source=source,
        )

    safe_best_effort(_run, label="review_closure.persist", default=None)


def queue_experience_candidate_safe(
    *,
    row: dict[str, Any],
    pending_path: Any,
) -> None:
    import json

    def _run() -> None:
        pending_path.parent.mkdir(parents=True, exist_ok=True)
        with pending_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    safe_best_effort(_run, label="review_closure.experience_candidate", default=None)
