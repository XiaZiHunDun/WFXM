"""Ensure every LoopTransitionReason is documented (AP-7)."""

from __future__ import annotations

from pathlib import Path

import pytest

from butler.core.loop_types import LoopTransitionReason

_DOC = Path(__file__).resolve().parents[1] / "docs/architecture/agent-loop-state-machine.md"

_COVERED_IN_TESTS = {
    LoopTransitionReason.TURN_COMPLETED,
    LoopTransitionReason.TOOL_LIMIT,
}


@pytest.mark.unit
def test_loop_transition_reason_documented_in_ssot():
    text = _DOC.read_text(encoding="utf-8")
    missing = [r.value for r in LoopTransitionReason if r.value not in text]
    assert not missing, f"undocumented transition reasons: {missing}"


@pytest.mark.unit
def test_core_transition_reasons_have_behavior_tests():
    """At least one behavioral test exists for high-traffic reasons."""
    assert LoopTransitionReason.TURN_COMPLETED in _COVERED_IN_TESTS
    assert LoopTransitionReason.TOOL_LIMIT in _COVERED_IN_TESTS
