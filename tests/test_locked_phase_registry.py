"""Tests for locked_phase_registry (ENG-11)."""

from __future__ import annotations

from butler.gateway.locked_phase_registry import (
    EARLY_EXIT_PHASE_NAMES,
    IN_CONTEXT_PHASE_NAMES,
    _in_context_entries,
    _pre_lock_entries,
)


def test_pre_lock_phase_order():
    names = [e.name for e in _pre_lock_entries()]
    assert names == [
        "normalizers_and_slash",
        "correction_intent",
        "github_issues_intent",
        "init_loop_role",
        "prompt_hooks",
    ]


def test_in_context_phase_order():
    names = [e.name for e in _in_context_entries()]
    assert names[0] == "augment_prompt"
    assert names[-1] == "format_turn_response"
    assert "execute_turn" in names


def test_exported_name_tuples_match():
    from butler.gateway.locked_phase_registry import PhaseKind

    assert EARLY_EXIT_PHASE_NAMES == tuple(
        e.name for e in _pre_lock_entries() if e.kind == PhaseKind.EARLY_EXIT
    )
    assert IN_CONTEXT_PHASE_NAMES == tuple(e.name for e in _in_context_entries())
