"""WorkflowGateStore contract registration and delegation."""

from __future__ import annotations

import butler.contracts.workflow_gate_impl  # noqa: F401 — register default store
from butler.contracts.workflow_gate_registry import get_workflow_gate


def test_workflow_gate_store_registered():
    gate = get_workflow_gate()
    assert gate is not None
    assert hasattr(gate, "check_workflow_step_approval")
    assert hasattr(gate, "format_pending_hint")
    assert hasattr(gate, "has_pending_gate")


def test_workflow_gate_confirm_flow_via_port(tmp_butler_home):
    sk = "port-sk"
    gate = get_workflow_gate()
    assert gate.check_workflow_step_approval(sk, "novel-factory", "review") is False
    from butler.human_gate import resolve_human_gate_message

    out = resolve_human_gate_message(sk, "确认", owner_verified=True)
    assert out
    assert gate.check_workflow_step_approval(sk, "novel-factory", "review") is True
