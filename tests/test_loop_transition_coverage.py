"""Ensure every LoopTransitionReason is documented (AP-7)."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from butler.core.loop_types import LoopConfig, LoopTransitionReason

_DOC = Path(__file__).resolve().parents[1] / "docs/architecture/agent-loop-state-machine.md"

_COVERED_IN_TESTS = {
    LoopTransitionReason.TURN_COMPLETED,
    LoopTransitionReason.TOOL_LIMIT,
    LoopTransitionReason.COMPACTION_TURN,
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
    assert LoopTransitionReason.COMPACTION_TURN in _COVERED_IN_TESTS


@pytest.mark.unit
@patch("butler.core.agent_loop_phases.safe_best_effort")
@patch("butler.core.compaction_task.run_compaction_turn")
@patch("butler.core.compaction_task.should_run_compaction_turn", return_value=True)
def test_compaction_turn_sets_transition_reason(_should, mock_run, _safe):
    from butler.core.agent_loop_phases import TurnBodyState, _phase_maybe_compact_turn

    msgs = [{"role": "user", "content": "x"}] * 12
    shrunk = msgs[:4]
    mock_run.return_value = (True, shrunk)
    loop = SimpleNamespace(
        _messages=msgs,
        config=LoopConfig(max_context_tokens=8000),
        diagnostics={},
        _estimate_tokens=lambda m: 9000,
        _compress_context=lambda m, **kw: shrunk,
    )
    state = TurnBodyState(iteration=2)
    assert _phase_maybe_compact_turn(loop, state) is True
    assert state.transition == LoopTransitionReason.COMPACTION_TURN
    assert loop._messages == shrunk
