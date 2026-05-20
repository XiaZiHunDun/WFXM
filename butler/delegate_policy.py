"""Delegation safety policy (from Hermes delegate_tool)."""

from __future__ import annotations

DELEGATE_BLOCKED_TOOLS = frozenset({
    "delegate_task",
    "run_workflow",
})

MAX_DELEGATE_DEPTH = 2
