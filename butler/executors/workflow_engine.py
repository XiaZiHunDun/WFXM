"""Workflow engine - generalized state machine for multi-step project workflows.

Inspired by AI-Incursion's novel-factory workflow_state.json pattern.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from butler.executors.base import BaseExecutor
from butler.storage.project_state import ProjectState

logger = logging.getLogger(__name__)


@dataclass
class WorkflowStep:
    id: str
    name: str
    description: str = ""
    required: bool = True
    depends_on: list[str] = field(default_factory=list)
    executor: str = "light-agent"
    auto: bool = False  # can be auto-executed without human approval


@dataclass
class WorkflowDef:
    """Defines a workflow as a sequence of phases and steps."""
    name: str
    description: str = ""
    phases: list[WorkflowPhase] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> WorkflowDef:
        phases = []
        for p in data.get("phases", []):
            steps = [WorkflowStep(**s) for s in p.get("steps", [])]
            phases.append(WorkflowPhase(
                id=p["id"],
                name=p["name"],
                description=p.get("description", ""),
                steps=steps,
            ))
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            phases=phases,
        )


@dataclass
class WorkflowPhase:
    id: str
    name: str
    description: str = ""
    steps: list[WorkflowStep] = field(default_factory=list)


class WorkflowEngine(BaseExecutor):
    """Drives multi-step workflows within a project."""

    name = "workflow"

    def __init__(self):
        self._workflow_defs: dict[str, WorkflowDef] = {}

    def register_workflow(self, workflow_def: WorkflowDef) -> None:
        self._workflow_defs[workflow_def.name] = workflow_def

    async def is_available(self) -> bool:
        return True

    async def execute(
        self,
        project_name: str,
        task: str,
        on_progress: Callable[[str], None] | None = None,
        **kwargs: Any,
    ) -> str:
        """Execute a workflow command.

        task format: "<workflow_name>:<command>" where command is:
        - "status" - get current status
        - "advance" - advance to next step
        - "init" - initialize workflow
        - "reset" - reset workflow state
        """
        parts = task.split(":", 1)
        workflow_name = parts[0].strip()
        command = parts[1].strip() if len(parts) > 1 else "status"

        wf_def = self._workflow_defs.get(workflow_name)
        if not wf_def:
            return json.dumps({"error": f"Workflow '{workflow_name}' not registered"})

        state = self._load_state(project_name)

        if command == "status":
            return self._get_status(wf_def, state)
        elif command == "init":
            return self._init_workflow(project_name, wf_def, state, kwargs)
        elif command == "advance":
            return self._advance(project_name, wf_def, state, kwargs)
        elif command == "reset":
            return self._reset(project_name, wf_def)
        else:
            return json.dumps({"error": f"Unknown command: {command}"})

    def _load_state(self, project_name: str) -> dict:
        from butler.core.project_manager import project_manager
        proj = project_manager.get_project(project_name)
        if not proj:
            return {}
        ps = ProjectState(proj.workspace)
        return ps.read_workflow_state()

    def _save_state(self, project_name: str, state: dict) -> None:
        from butler.core.project_manager import project_manager
        proj = project_manager.get_project(project_name)
        if proj:
            ps = ProjectState(proj.workspace)
            ps.update_workflow_state(state)

    def _get_status(self, wf_def: WorkflowDef, state: dict) -> str:
        if not state:
            return json.dumps({
                "workflow": wf_def.name,
                "status": "not_initialized",
                "message": f"工作流 '{wf_def.name}' 尚未初始化",
            }, ensure_ascii=False)

        return json.dumps({
            "workflow": wf_def.name,
            "current_phase": state.get("current_phase", ""),
            "current_step": state.get("current_step", ""),
            "status": state.get("status", ""),
            "completed_steps": state.get("completed_steps", []),
            "last_updated": state.get("last_updated", ""),
        }, ensure_ascii=False)

    def _init_workflow(self, project_name: str, wf_def: WorkflowDef, state: dict, kwargs: dict) -> str:
        if state.get("status") == "active":
            return json.dumps({"error": "工作流已在进行中，如需重置请使用 reset"}, ensure_ascii=False)

        first_phase = wf_def.phases[0] if wf_def.phases else None
        first_step = first_phase.steps[0] if first_phase and first_phase.steps else None

        new_state = {
            "workflow": wf_def.name,
            "status": "active",
            "current_phase": first_phase.id if first_phase else "",
            "current_step": first_step.id if first_step else "",
            "completed_steps": [],
            "initialized_at": datetime.utcnow().isoformat(),
            **{k: v for k, v in kwargs.items() if k in ("project_title", "metadata")},
        }
        self._save_state(project_name, new_state)
        return json.dumps({
            "success": True,
            "message": f"工作流 '{wf_def.name}' 已初始化",
            "current_phase": new_state["current_phase"],
            "current_step": new_state["current_step"],
        }, ensure_ascii=False)

    def _advance(self, project_name: str, wf_def: WorkflowDef, state: dict, kwargs: dict) -> str:
        if state.get("status") != "active":
            return json.dumps({"error": "工作流未处于活动状态"}, ensure_ascii=False)

        current_phase_id = state.get("current_phase", "")
        current_step_id = state.get("current_step", "")
        completed = state.get("completed_steps", [])

        if current_step_id and current_step_id not in completed:
            completed.append(current_step_id)

        next_step, next_phase = self._find_next(wf_def, current_phase_id, current_step_id)

        if next_step is None:
            state["status"] = "completed"
            state["completed_steps"] = completed
            state["completed_at"] = datetime.utcnow().isoformat()
            self._save_state(project_name, state)
            return json.dumps({
                "success": True,
                "message": f"工作流 '{wf_def.name}' 已完成！",
                "status": "completed",
            }, ensure_ascii=False)

        state["current_phase"] = next_phase.id
        state["current_step"] = next_step.id
        state["completed_steps"] = completed
        self._save_state(project_name, state)

        return json.dumps({
            "success": True,
            "message": f"已推进到: {next_phase.name} / {next_step.name}",
            "current_phase": next_phase.id,
            "current_step": next_step.id,
            "step_description": next_step.description,
            "executor": next_step.executor,
        }, ensure_ascii=False)

    def _find_next(
        self, wf_def: WorkflowDef, current_phase_id: str, current_step_id: str
    ) -> tuple[WorkflowStep | None, WorkflowPhase | None]:
        found_current = False
        for phase in wf_def.phases:
            for step in phase.steps:
                if found_current:
                    return step, phase
                if step.id == current_step_id:
                    found_current = True
        return None, None

    def _reset(self, project_name: str, wf_def: WorkflowDef) -> str:
        self._save_state(project_name, {
            "workflow": wf_def.name,
            "status": "reset",
            "reset_at": datetime.utcnow().isoformat(),
        })
        return json.dumps({
            "success": True,
            "message": f"工作流 '{wf_def.name}' 已重置",
        }, ensure_ascii=False)
