"""Dev delegate result finalization (ENG-2)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState


def peek_dev_engine_summary(session_key: str, role: str) -> dict[str, Any] | None:
    """Read DevState summary without popping (for background delegate jobs)."""
    from butler.dev_engine.delegate_finalize_ops import peek_dev_engine_summary_safe

    return cast(dict[str, Any] | None, peek_dev_engine_summary_safe(session_key, role))


def attach_dev_engine_summary(state: DelegateRunState, payload: dict[str, Any]) -> None:
    """Attach DevState summary to delegate result when engine active (6g, DA6)."""
    norm = state.role.replace("_agent", "").strip().lower()
    if norm != "dev":
        return
    from butler.dev_engine.delegate_finalize_ops import (
        apply_experience_lifecycle_safe,
        attach_dev_engine_payload_safe,
        attach_review_handoff_safe,
        record_dev_delegate_outcome_safe,
        try_extract_experience_safe,
    )

    ds = attach_dev_engine_payload_safe(state, payload)
    if ds is None:
        return
    attach_review_handoff_safe(state, payload)
    lifecycle = apply_experience_lifecycle_safe(ds, state)
    if lifecycle:
        payload.setdefault("dev_engine", {})["experience_lifecycle"] = lifecycle
    try_extract_experience_safe(ds, state)
    record_dev_delegate_outcome_safe(ds, state)


def try_extract_experience(ds: Any, state: DelegateRunState) -> None:
    """Best-effort: extract and persist a coding experience on task success."""
    from butler.dev_engine.delegate_finalize_ops import try_extract_experience_safe

    try_extract_experience_safe(ds, state)


__all__ = [
    "attach_dev_engine_summary",
    "peek_dev_engine_summary",
    "try_extract_experience",
]
