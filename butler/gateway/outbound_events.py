"""Typed outbound milestone events for gateway / workflow / delegate (Dify/Langflow subset)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class OutboundEvent:
    kind: str
    phase: str = ""
    name: str = ""
    detail: str = ""
    step_index: int = 0
    step_total: int = 0
    monotonic: float = field(default_factory=time.monotonic)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "phase": self.phase,
            "name": self.name,
            "detail": (self.detail or "")[:200],
            "step_index": self.step_index,
            "step_total": self.step_total,
            "monotonic": self.monotonic,
            **self.extra,
        }


def workflow_event(
    workflow_name: str,
    step_id: str,
    *,
    phase: str,
    step_index: int = 0,
    step_total: int = 0,
    error: str = "",
) -> OutboundEvent:
    return OutboundEvent(
        kind="workflow_step",
        phase=phase,
        name=f"{workflow_name}:{step_id}",
        detail=error,
        step_index=step_index,
        step_total=step_total,
    )


def delegate_event(role: str, *, phase: str, preview: str = "") -> OutboundEvent:
    return OutboundEvent(
        kind="delegate",
        phase=phase,
        name=role,
        detail=preview,
    )


def tool_event(tool_name: str, *, phase: str = "start") -> OutboundEvent:
    return OutboundEvent(
        kind="tool",
        phase=phase,
        name=tool_name,
    )


def stream_event(*, phase: str = "delta", chars: int = 0) -> OutboundEvent:
    return OutboundEvent(
        kind="stream",
        phase=phase,
        detail=str(chars),
    )
