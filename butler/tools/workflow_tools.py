"""Workflow listing tool (B9 workflow-as-tool complement)."""

from __future__ import annotations

import json
from typing import Any


def tool_list_workflows(**_: Any) -> str:
    from butler.execution_context import get_current_orchestrator, get_current_session_key

    orch = get_current_orchestrator()
    if orch is None:
        return json.dumps({"error": "no orchestrator context"}, ensure_ascii=False)
    pm = getattr(orch, "project_manager", None)
    if pm is None:
        return json.dumps({"error": "no project manager"}, ensure_ascii=False)
    project = pm.get_current(session_key=str(get_current_session_key() or ""))
    from butler.workflows.loader import list_workflows_for_project

    workflows = list_workflows_for_project(project)
    rows = [
        {
            "name": wf.name,
            "description": wf.description,
            "runnable": wf.runnable,
            "steps": len(wf.steps),
            "step_ids": [s.id for s in wf.steps],
        }
        for wf in workflows
    ]
    return json.dumps({"workflows": rows, "count": len(rows)}, ensure_ascii=False)


def register_workflow_tools(register_fn) -> None:
    register_fn(
        name="list_workflows",
        description=(
            "List workflows declared for the current project (project.yaml + "
            ".butler/workflows/). Use before run_workflow."
        ),
        schema={"type": "object", "properties": {}},
        handler=lambda _args: tool_list_workflows(),
        toolset="delegation",
    )
