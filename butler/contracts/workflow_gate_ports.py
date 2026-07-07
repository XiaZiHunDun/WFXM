"""Workflow / injection human-gate Protocol (L7) — workflow runner ↔ gateway storage."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class WorkflowGateStore(Protocol):
    """Session-scoped workflow step + injection review gates."""

    def check_workflow_step_approval(
        self,
        session_key: str,
        workflow_name: str,
        step_id: str,
    ) -> bool: ...

    def format_pending_hint(self, session_key: str) -> str: ...

    def has_pending_gate(self, session_key: str) -> bool: ...


__all__ = ["WorkflowGateStore"]
