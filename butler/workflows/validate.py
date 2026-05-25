"""Workflow definition validation (Langflow schema discipline subset)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.workflows.schema import WorkflowDef, WorkflowStepDef, parse_workflow_data

WORKFLOW_SCHEMA_VERSION = "1"


def validate_workflow_def(workflow: WorkflowDef) -> list[str]:
    errors: list[str] = []
    if not workflow.name.strip():
        errors.append("workflow.name is required")
    if not workflow.steps:
        errors.append("workflow has no steps")
        return errors

    ids = [s.id for s in workflow.steps]
    if len(ids) != len(set(ids)):
        errors.append("duplicate step ids")

    id_set = set(ids)
    for step in workflow.steps:
        errors.extend(_validate_step(step, id_set=id_set))

    errors.extend(_validate_dag(workflow.steps))
    if str(workflow.schema_version or "1") != WORKFLOW_SCHEMA_VERSION:
        errors.append(
            f"schema_version {workflow.schema_version!r} != supported {WORKFLOW_SCHEMA_VERSION}"
        )
    return errors


def _validate_step(step: WorkflowStepDef, *, id_set: set[str]) -> list[str]:
    out: list[str] = []
    if not step.id.strip():
        out.append("step missing id")
    if not step.role.strip():
        out.append(f"step {step.id}: missing role")
    if not step.task.strip():
        out.append(f"step {step.id}: missing task")
    for dep in step.depends_on:
        if dep not in id_set:
            out.append(f"step {step.id}: unknown dependency {dep!r}")
        if dep == step.id:
            out.append(f"step {step.id}: self dependency")
    return out


def _validate_dag(steps: list[WorkflowStepDef]) -> list[str]:
    graph = {s.id: list(s.depends_on) for s in steps}
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[str] = []

    def _visit(node: str) -> None:
        if node in visited:
            return
        if node in visiting:
            errors.append(f"cycle detected at step {node}")
            return
        visiting.add(node)
        for dep in graph.get(node, []):
            _visit(dep)
        visiting.discard(node)
        visited.add(node)

    for sid in graph:
        _visit(sid)
    return errors


def validate_workflow_file(path: Path) -> tuple[WorkflowDef | None, list[str]]:
    if not path.is_file():
        return None, [f"file not found: {path}"]
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return None, [f"parse error: {exc}"]
    if not isinstance(data, dict):
        return None, ["workflow file must be a mapping"]
    wf = parse_workflow_data(data, source=str(path))
    if wf is None:
        return None, ["invalid workflow structure"]
    return wf, validate_workflow_def(wf)


def validate_project_workflow(project: Any, name: str) -> list[str]:
    from butler.workflows.loader import resolve_workflow

    wf = resolve_workflow(project, name)
    if wf is None:
        return [f"workflow not found: {name}"]
    return validate_workflow_def(wf)
