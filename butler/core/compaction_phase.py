"""Compaction phase and initial-context injection (Codex compact.rs subset)."""

from __future__ import annotations

from enum import Enum
from typing import Any


class CompactionPhase(str, Enum):
    PRE_TURN = "pre_turn"
    MID_TURN = "mid_turn"
    REACTIVE = "reactive"
    STANDALONE = "standalone"


class CompactionReason(str, Enum):
    AUTO = "auto"
    MODEL_DOWNSHIFT = "model_downshift"
    USER_REQUESTED = "user_requested"
    OVERFLOW = "overflow"


class InitialContextInjection(str, Enum):
    """Where to place summary relative to last user message."""

    DO_NOT_INJECT = "do_not_inject"
    BEFORE_LAST_USER = "before_last_user"


def resolve_compaction_context(
    *,
    iteration: int = 1,
    explicit_turn: bool = False,
    reactive: bool = False,
) -> tuple[CompactionPhase, InitialContextInjection, CompactionReason]:
    if reactive:
        return (
            CompactionPhase.REACTIVE,
            InitialContextInjection.BEFORE_LAST_USER,
            CompactionReason.OVERFLOW,
        )
    if explicit_turn and iteration <= 1:
        return (
            CompactionPhase.PRE_TURN,
            InitialContextInjection.DO_NOT_INJECT,
            CompactionReason.AUTO,
        )
    if iteration > 1:
        return (
            CompactionPhase.MID_TURN,
            InitialContextInjection.BEFORE_LAST_USER,
            CompactionReason.AUTO,
        )
    return (
        CompactionPhase.PRE_TURN,
        InitialContextInjection.DO_NOT_INJECT,
        CompactionReason.AUTO,
    )


def record_compaction_diagnostics(
    diagnostics: dict[str, Any] | None,
    *,
    phase: CompactionPhase,
    reason: CompactionReason,
    injection: InitialContextInjection,
) -> None:
    if diagnostics is None:
        return
    diagnostics["compaction_phase"] = phase.value
    diagnostics["compaction_reason"] = reason.value
    diagnostics["compaction_initial_injection"] = injection.value


def mid_turn_compact_enabled() -> bool:
    from butler.env_parse import env_truthy

    return env_truthy("BUTLER_MID_TURN_COMPACT", default=True)


def apply_summary_placement(
    system: list[dict],
    head_tail: list[dict],
    summary_msg: dict,
    injection: InitialContextInjection,
) -> list[dict]:
    """Build compressed message list with Codex-style summary placement."""
    if injection == InitialContextInjection.DO_NOT_INJECT:
        return system + [summary_msg] + head_tail

    if not head_tail:
        return system + [summary_msg]

    last_user_idx = -1
    for i in range(len(head_tail) - 1, -1, -1):
        if head_tail[i].get("role") == "user":
            content = str(head_tail[i].get("content") or "")
            if "[CONTEXT COMPACTION" in content:
                continue
            last_user_idx = i
            break

    if last_user_idx < 0:
        return system + [summary_msg] + head_tail

    return (
        system
        + head_tail[:last_user_idx]
        + [summary_msg]
        + head_tail[last_user_idx:]
    )


def should_skip_post_compact_reanchor(diagnostics: dict[str, Any] | None) -> bool:
    """Mid-turn compact should not re-inject full skills/memory anchors."""
    if not mid_turn_compact_enabled():
        return False
    if not isinstance(diagnostics, dict):
        return False
    return diagnostics.get("compaction_phase") == CompactionPhase.MID_TURN.value


__all__ = [
    "CompactionPhase",
    "CompactionReason",
    "InitialContextInjection",
    "apply_summary_placement",
    "mid_turn_compact_enabled",
    "record_compaction_diagnostics",
    "resolve_compaction_context",
    "should_skip_post_compact_reanchor",
]
