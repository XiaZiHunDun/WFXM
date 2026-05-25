"""Typed workflow definitions from ``project.yaml`` and workspace files."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from butler.config import ModelConfig


@dataclass
class WorkflowStepDef:
    id: str
    role: str
    task: str
    depends_on: list[str] = field(default_factory=list)
    tools: list[str] | None = None
    requires_approval: bool = False
    model: ModelConfig | None = None
    output_keys: list[str] = field(default_factory=lambda: ["output"])
    max_retries: int = 1
    handoff_only: bool = True
    clear_child_transcript: bool = False
    output_schema: dict[str, Any] | None = None
    supervisor_note: str = ""


@dataclass
class WorkflowDef:
    name: str
    description: str = ""
    steps: list[WorkflowStepDef] = field(default_factory=list)
    source: str = "project"
    schema_version: str = "1"

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
    model_cfg: ModelConfig | None = None
    model_raw = raw.get("model")
    if isinstance(model_raw, str) and model_raw.strip():
        from butler.model_resolve import parse_model_spec

        model_cfg = parse_model_spec(model_raw.strip())
    elif isinstance(model_raw, dict):
        model_cfg = ModelConfig.from_dict(model_raw)
    from butler.workflows.variables import extract_output_keys

    try:
        max_retries = max(1, int(raw.get("max_retries", 1)))
    except (TypeError, ValueError):
        max_retries = 1

    handoff_only = raw.get("handoff_only", True)
    if isinstance(handoff_only, str):
        handoff_only = handoff_only.strip().lower() not in ("0", "false", "no", "off")

    clear_child = raw.get("clear_child_transcript", False)
    if isinstance(clear_child, str):
        clear_child = clear_child.strip().lower() in ("1", "true", "yes", "on")

    output_schema = raw.get("output_schema")
    if not isinstance(output_schema, dict):
        output_schema = None

    supervisor_note = str(raw.get("supervisor_note") or raw.get("supervisor") or "").strip()

    return WorkflowStepDef(
        id=step_id,
        role=role,
        task=task,
        depends_on=[str(d).strip() for d in deps if str(d).strip()],
        tools=tools,
        requires_approval=bool(raw.get("requires_approval", False)),
        model=model_cfg,
        output_keys=extract_output_keys(raw),
        max_retries=max_retries,
        handoff_only=bool(handoff_only),
        clear_child_transcript=bool(clear_child),
        output_schema=output_schema,
        supervisor_note=supervisor_note,
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
        schema_version=str(data.get("schema_version") or "1").strip() or "1",
    )


__all__ = ["WorkflowDef", "WorkflowStepDef", "parse_step", "parse_workflow_data"]
