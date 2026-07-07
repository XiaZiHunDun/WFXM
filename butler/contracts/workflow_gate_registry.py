"""Runtime registration for WorkflowGateStore."""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.contracts.workflow_gate_ports import WorkflowGateStore

_LOCK = threading.RLock()
_WORKFLOW_GATE: WorkflowGateStore | None = None


def set_workflow_gate(store: WorkflowGateStore | None) -> None:
    global _WORKFLOW_GATE
    with _LOCK:
        _WORKFLOW_GATE = store


def get_workflow_gate() -> WorkflowGateStore:
    with _LOCK:
        global _WORKFLOW_GATE
        if _WORKFLOW_GATE is None:
            from butler.contracts.workflow_gate_impl import HumanGateWorkflowStore

            _WORKFLOW_GATE = HumanGateWorkflowStore()
        return _WORKFLOW_GATE


__all__ = ["get_workflow_gate", "set_workflow_gate"]
