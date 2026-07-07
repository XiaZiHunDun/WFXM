"""Default WorkflowGateStore — wraps ``butler.human_gate`` (L7)."""

from __future__ import annotations

from butler.contracts.workflow_gate_registry import set_workflow_gate
from butler.human_gate import (
    check_workflow_step_approval,
    format_pending_hint,
    has_pending_gate,
)


class HumanGateWorkflowStore:
    def check_workflow_step_approval(
        self,
        session_key: str,
        workflow_name: str,
        step_id: str,
    ) -> bool:
        return bool(check_workflow_step_approval(session_key, workflow_name, step_id))

    def format_pending_hint(self, session_key: str) -> str:
        return str(format_pending_hint(session_key))

    def has_pending_gate(self, session_key: str) -> bool:
        return bool(has_pending_gate(session_key))


def register_default_workflow_gate() -> None:
    set_workflow_gate(HumanGateWorkflowStore())


register_default_workflow_gate()

__all__ = ["HumanGateWorkflowStore", "register_default_workflow_gate"]
