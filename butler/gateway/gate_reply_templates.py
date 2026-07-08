"""Re-export L7 gate reply templates (gateway compat shim)."""

from __future__ import annotations

from butler.gate_reply_templates import (
    injection_gate_confirmed_hint,
    injection_gate_pending_hint,
    workflow_gate_confirmed_hint,
    workflow_gate_pending_hint,
)

__all__ = [
    "injection_gate_confirmed_hint",
    "injection_gate_pending_hint",
    "workflow_gate_confirmed_hint",
    "workflow_gate_pending_hint",
]
