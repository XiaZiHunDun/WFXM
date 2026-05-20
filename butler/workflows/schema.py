"""Typed workflow definitions from ``project.yaml`` and workspace files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class WorkflowStepDef:
    id: str
    role: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    tools: list[str] | None = None
    requires_approval: bool = False


@dataclass
class WorkflowDef:
    name: str
    description: str = ""
    steps: list[WorkflowStepDef] = field(default_factory=list)
    source: str = "project"

    @property
    def runnable(self) -> bool:
        return bool(self.steps)


def parse_step(raw: dict[str, Any]) -> WorkflowStepDef | None:
    if not isinstance(raw, dict):
        return None
    step_id = str(raw.get("id") or "").strip()
    role = str(raw.get("role") or "").strip()
    task = str(raw.get("task") or "").strip()
    if not step_id or not role or not task:
        return None
    deps = raw.get("depends_on") or raw.get("depends") or []
    if isinstance(deps, str):
        deps = [deps]
    tools_raw = raw.get("tools")
    tools = None
    if isinstance(tools_raw, list):
        tools = [str(t).strip() for t in tools_raw if str(t).strip()]
    return WorkflowStepDef(
        id=step_id,
        role=role,
        task=task,
        depends_on=[str(d).strip() for d in deps if str(d).strip()],
        tools=tools,
        requires_approval=bool(raw.get("requires_approval", False)),
    )


def parse_workflow_data(data: dict[str, Any], *, source: str = "project") -> WorkflowDef | None:
    name = str(data.get("name") or "").strip()
    if not name:
        return None
    steps: list[WorkflowStepDef] = []
    for raw in data.get("steps") or []:
        if isinstance(raw, dict):
            step = parse_step(raw)
            if step is not None:
                steps.append(step)
    return WorkflowDef(
        name=name,
        description=str(data.get("description") or "").strip(),
        steps=steps,
        source=source,
    )


__all__ = ["WorkflowDef", "WorkflowStepDef", "parse_step", "parse_workflow_data"]
