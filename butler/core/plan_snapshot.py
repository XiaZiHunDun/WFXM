"""Structured workflow plan snapshot (MetaGPT / 主线 N P1 subset)."""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PlanStep:
    id: str
    status: str = "pending"
    note: str = ""


@dataclass
class PlanSnapshot:
    goal: str = ""
    workflow: str = ""
    steps: list[PlanStep] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "goal": self.goal,
            "workflow": self.workflow,
            "steps": [asdict(s) for s in self.steps],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


def qa_response_is_fail(text: str) -> bool:
    head = (text or "").strip().splitlines()[0].strip().upper() if text else ""
    return head.startswith("FAIL")


def build_plan_snapshot(
    workflow_name: str,
    *,
    goal: str = "",
    step_ids: list[str] | None = None,
    outcomes: dict[str, str] | None = None,
) -> PlanSnapshot:
    snap = PlanSnapshot(goal=goal or workflow_name, workflow=workflow_name)
    for sid in step_ids or []:
        status = (outcomes or {}).get(sid, "pending")
        snap.steps.append(PlanStep(id=sid, status=status))
    return snap


def update_step_outcome(snap: PlanSnapshot, step_id: str, *, success: bool, note: str = "") -> None:
    status = "ok" if success else "fail"
    for step in snap.steps:
        if step.id == step_id:
            step.status = status
            if note:
                step.note = note[:500]
            return
    snap.steps.append(PlanStep(id=step_id, status=status, note=note[:500]))


def replan_implement_task(base_task: str, qa_feedback: str, *, attempt: int) -> str:
    fb = (qa_feedback or "").strip()[:3000]
    return (
        f"{base_task.rstrip()}\n\n"
        f"## QA 未通过（重跑 implement #{attempt}）\n"
        f"请根据以下审查结论修复实现，完成后更新 HANDOFF。\n\n{fb}"
    )


__all__ = [
    "PlanSnapshot",
    "PlanStep",
    "build_plan_snapshot",
    "qa_response_is_fail",
    "replan_implement_task",
    "update_step_outcome",
]
