"""Declarative locked-turn phase order (ENG-11)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from butler.gateway.locked_phases import LockedTurnState
    from butler.gateway.message_handler import ButlerMessageHandler


class PhaseKind(str, Enum):
    EARLY_EXIT = "early_exit"
    SETUP = "setup"
    VALIDATE_EXIT = "validate_exit"
    BODY = "body"


@dataclass(frozen=True)
class LockedPhaseEntry:
    name: str
    kind: PhaseKind
    fn: Any
    needs_handler: bool = True


def _pre_lock_entries() -> tuple[LockedPhaseEntry, ...]:
    from butler.gateway.locked_phases import (
        _phase_apply_correction_intent,
        _phase_apply_github_issues_intent,
        _phase_apply_normalizers_and_slash,
        _phase_apply_prompt_hooks,
        _phase_init_loop_role,
    )

    return (
        LockedPhaseEntry("normalizers_and_slash", PhaseKind.EARLY_EXIT, _phase_apply_normalizers_and_slash),
        LockedPhaseEntry("correction_intent", PhaseKind.EARLY_EXIT, _phase_apply_correction_intent),
        LockedPhaseEntry("github_issues_intent", PhaseKind.EARLY_EXIT, _phase_apply_github_issues_intent),
        LockedPhaseEntry("init_loop_role", PhaseKind.SETUP, _phase_init_loop_role),
        LockedPhaseEntry("prompt_hooks", PhaseKind.EARLY_EXIT, _phase_apply_prompt_hooks, needs_handler=False),
    )


def _in_context_entries() -> tuple[LockedPhaseEntry, ...]:
    from butler.gateway.locked_phases import (
        _phase_augment_prompt,
        _phase_execute_turn,
        _phase_finalize_turn,
        _phase_format_turn_response,
        _phase_hygiene_compress,
        _phase_prefetch_and_callbacks,
        _phase_resolve_turn_budget,
        _phase_validate_loop_messages,
    )

    return (
        LockedPhaseEntry("augment_prompt", PhaseKind.SETUP, _phase_augment_prompt),
        LockedPhaseEntry("validate_loop_messages", PhaseKind.VALIDATE_EXIT, _phase_validate_loop_messages, needs_handler=False),
        LockedPhaseEntry("resolve_turn_budget", PhaseKind.BODY, _phase_resolve_turn_budget, needs_handler=False),
        LockedPhaseEntry("hygiene_compress", PhaseKind.BODY, _phase_hygiene_compress),
        LockedPhaseEntry("prefetch_and_callbacks", PhaseKind.BODY, _phase_prefetch_and_callbacks),
        LockedPhaseEntry("execute_turn", PhaseKind.BODY, _phase_execute_turn, needs_handler=False),
        LockedPhaseEntry("finalize_turn", PhaseKind.BODY, _phase_finalize_turn),
        LockedPhaseEntry("format_turn_response", PhaseKind.BODY, _phase_format_turn_response),
    )


EARLY_EXIT_PHASE_NAMES: tuple[str, ...] = tuple(
    e.name for e in _pre_lock_entries() if e.kind == PhaseKind.EARLY_EXIT
)
IN_CONTEXT_PHASE_NAMES: tuple[str, ...] = tuple(e.name for e in _in_context_entries())


def run_pre_lock_phases(
    handler: "ButlerMessageHandler",
    state: "LockedTurnState",
) -> Optional[str]:
    """Phases before ``use_execution_context`` (may return early)."""
    for entry in _pre_lock_entries():
        if entry.kind == PhaseKind.EARLY_EXIT:
            response = _call_early_exit(handler, state, entry)
            if response is None:
                continue
            if entry.name == "github_issues_intent":
                from butler.gateway.gateway_transcript import record_gateway_tool_action

                record_gateway_tool_action(
                    state.session_key,
                    tool_name="mcp_github_lst_repo_issues",
                    args_preview=state.text.strip()[:400],
                )
            return response
        _call_setup(handler, state, entry)
    return None


def run_augment_phase(
    handler: "ButlerMessageHandler",
    state: "LockedTurnState",
) -> None:
    """First in-context step (before loop bind)."""
    from butler.gateway.locked_phases import _phase_augment_prompt

    _phase_augment_prompt(handler, state)


def run_in_context_phases(
    handler: "ButlerMessageHandler",
    state: "LockedTurnState",
    *,
    welcome_prefix: str = "",
) -> Optional[str]:
    """Phases inside ``use_execution_context`` (after loop bind)."""
    for entry in _in_context_entries():
        if entry.name == "augment_prompt":
            continue
        if entry.kind == PhaseKind.VALIDATE_EXIT:
            from typing import cast

            response = cast(Optional[str], entry.fn(state))
            if response is not None:
                return response
            continue
        if entry.kind == PhaseKind.BODY and entry.name == "format_turn_response":
            entry.fn(handler, state, welcome_prefix=welcome_prefix)
            continue
        _call_setup(handler, state, entry)
    return None


def _call_early_exit(
    handler: "ButlerMessageHandler",
    state: "LockedTurnState",
    entry: LockedPhaseEntry,
) -> Optional[str]:
    from typing import cast

    if entry.needs_handler:
        return cast(Optional[str], entry.fn(handler, state))
    return cast(Optional[str], entry.fn(state))


def _call_setup(
    handler: "ButlerMessageHandler",
    state: "LockedTurnState",
    entry: LockedPhaseEntry,
) -> None:
    if entry.needs_handler:
        entry.fn(handler, state)
    else:
        entry.fn(state)


__all__ = [
    "EARLY_EXIT_PHASE_NAMES",
    "IN_CONTEXT_PHASE_NAMES",
    "LockedPhaseEntry",
    "PhaseKind",
    "run_augment_phase",
    "run_in_context_phases",
    "run_pre_lock_phases",
]
