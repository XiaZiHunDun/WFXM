"""Project state management - reads/writes project.yaml and workflow_state.json."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml


class ProjectState:
    """Manages a single project's state files."""

    def __init__(self, workspace: Path):
        self.workspace = workspace
        self.config_file = workspace / "project.yaml"
        self.workflow_state_file = workspace / "workflow_state.json"

    def read_config(self) -> dict[str, Any]:
        if self.config_file.exists():
            with open(self.config_file, encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        return {}

    def write_config(self, data: dict[str, Any]) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        with open(self.config_file, "w", encoding="utf-8") as f:
            yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def read_workflow_state(self) -> dict[str, Any]:
        if self.workflow_state_file.exists():
            with open(self.workflow_state_file, encoding="utf-8") as f:
                return json.load(f)
        return {}

    def update_workflow_state(self, updates: dict[str, Any]) -> dict[str, Any]:
        state = self.read_workflow_state()
        state.update(updates)
        state["last_updated"] = datetime.utcnow().isoformat()
        self.workspace.mkdir(parents=True, exist_ok=True)
        with open(self.workflow_state_file, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return state
