"""Development loop state machine — PLAN→LOCATE→EDIT→VERIFY→FIX.

Formal model from v4-dev-engine-theory.md §2.3:
  δ_dev: Σ_dev × Event_dev → Σ_dev
  Termination: DT2 — bounded by I_max × (1 + K_max)
"""

from __future__ import annotations

from butler.env_parse import int_env
import logging
import os
from pathlib import Path
from typing import Any

from butler.dev_engine.dev_state import (
    DevPhase,
    DevState,
    EditRecord,
    VerifyStatus,
)

logger = logging.getLogger(__name__)


def create_dev_state(
    task_description: str = "",
    *,
    max_fix_rounds: int | None = None,
    max_iterations: int | None = None,
    task_id: str = "",
) -> DevState:
    """Create a new DevState for a development task.

    If task_id is provided, registers with the global MetricsCollector.
    """
    import uuid

    env_fix = int_env("BUTLER_DEV_MAX_FIX_ROUNDS", 3)
    if max_fix_rounds is None:
        try:
            from butler.ops.eval_config_overrides import effective_dev_max_fix_rounds

            k_max = effective_dev_max_fix_rounds(env_fix)
        except Exception:
            k_max = env_fix
    else:
        k_max = max_fix_rounds
    i_max = max_iterations or 24
    state = DevState(
        task_description=task_description,
        max_fix_rounds=k_max,
        max_iterations=i_max,
    )

    tid = task_id or uuid.uuid4().hex[:12]
    state._metrics_task_id = tid  # type: ignore[attr-defined]
    try:
        from butler.dev_engine.dev_metrics import get_collector
        get_collector().on_task_start(tid, task_description)
    except Exception:
        pass

    return state


def transition(state: DevState, event: str, **kwargs: Any) -> DevState:
    """Apply a state transition (Definition D7).

    Returns the updated state. Enforces DT2 termination.
    Emits metrics events to the global MetricsCollector.
    """
    phase = state.phase

    if state.is_terminal:
        logger.warning("Attempted transition on terminal state %s", phase.value)
        return state

    if state.should_terminate():
        _emit_metrics(state, phase.value, "terminate", DevPhase.STUCK.value)
        state.phase = DevPhase.STUCK
        logger.info("Dev loop terminated: iteration/fix limit reached")
        return state

    transitions = _TRANSITION_TABLE.get((phase, event))
    if transitions is None:
        logger.warning("Invalid transition: (%s, %s)", phase.value, event)
        return state

    new_phase = transitions
    state.advance_phase(new_phase)

    if event == "fix_applied":
        if not state.record_fix_attempt():
            new_phase = DevPhase.STUCK
            state.phase = DevPhase.STUCK
            logger.info("Fix limit K_max reached, entering STUCK")

    if event == "verify_fail":
        from butler.dev_engine.dev_state import VerifyResult

        vr = kwargs.get("verify_result")
        if isinstance(vr, VerifyResult):
            state.verify_result = vr
            state.diagnostics = list(vr.diagnostics)

    if event == "verify_pass":
        from butler.dev_engine.dev_state import VerifyResult

        state.verify_result = VerifyResult(status=VerifyStatus.PASS)
        state.diagnostics = []

    if event == "edit_success":
        record = kwargs.get("edit_record")
        if isinstance(record, EditRecord):
            state.record_edit(record)

    _emit_metrics(state, phase.value, event, state.phase.value)
    return state


def _emit_metrics(state: DevState, from_phase: str, event: str, to_phase: str) -> None:
    """Emit transition event to the global MetricsCollector."""
    try:
        from butler.dev_engine.dev_metrics import get_collector
        task_id = getattr(state, "_metrics_task_id", "")
        if task_id:
            get_collector().on_transition(task_id, from_phase, event, to_phase)
    except Exception:
        pass


_TRANSITION_TABLE: dict[tuple[DevPhase, str], DevPhase] = {
    (DevPhase.PLAN, "plan_complete"): DevPhase.LOCATE,
    (DevPhase.PLAN, "plan_trivial"): DevPhase.EDIT,
    (DevPhase.LOCATE, "files_found"): DevPhase.EDIT,
    (DevPhase.LOCATE, "not_found"): DevPhase.PLAN,
    (DevPhase.LOCATE, "locate_timeout"): DevPhase.STUCK,
    (DevPhase.EDIT, "edit_success"): DevPhase.VERIFY,
    (DevPhase.EDIT, "edit_conflict"): DevPhase.LOCATE,
    (DevPhase.EDIT, "edit_fail"): DevPhase.FIX,
    (DevPhase.VERIFY, "verify_pass"): DevPhase.DONE,
    (DevPhase.VERIFY, "verify_fail"): DevPhase.FIX,
    (DevPhase.VERIFY, "verify_skip"): DevPhase.REVIEW,
    (DevPhase.FIX, "fix_applied"): DevPhase.VERIFY,
    (DevPhase.FIX, "fix_rollback"): DevPhase.PLAN,
    (DevPhase.REVIEW, "owner_approve"): DevPhase.DONE,
    (DevPhase.REVIEW, "owner_reject"): DevPhase.PLAN,
}


def get_valid_events(phase: DevPhase) -> list[str]:
    """Return valid events for the current phase."""
    return [event for (p, event) in _TRANSITION_TABLE if p == phase]


def dev_loop_summary(state: DevState) -> dict[str, Any]:
    """Generate a summary dict suitable for tool response."""
    return {
        "phase": state.phase.value,
        "is_terminal": state.is_terminal,
        "iteration": state.iteration,
        "fix_count": state.fix_count,
        "edit_count": len(state.edit_history),
        "verify_status": state.verify_result.status.value,
        "valid_events": get_valid_events(state.phase),
        "task": state.task_description[:200],
    }
