"""Project registry and management."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from butler.config.settings import ModelConfig, LayeredModelConfig
from butler.storage.project_state import ProjectState

logger = logging.getLogger(__name__)


@dataclass
class Project:
    name: str
    type: str  # software | content | research
    description: str
    status: str = "active"
    workspace: Path = field(default_factory=lambda: Path("."))
    models: dict[str, ModelConfig] = field(default_factory=dict)
    workflows: list[dict[str, str]] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: Path) -> Project:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        workspace = path.parent
        models_raw = data.get("models", {})
        models = {k: ModelConfig.from_dict(v) for k, v in models_raw.items()} if models_raw else {}
        return cls(
            name=data.get("name", workspace.name),
            type=data.get("type", "software"),
            description=data.get("description", ""),
            status=data.get("status", "active"),
            workspace=workspace,
            models=models,
            workflows=data.get("workflows", []),
            tools=data.get("tools", []),
        )

    def resolve_model(self, role: str, runtime_override: ModelConfig | None = None) -> ModelConfig:
        """Three-level merge: system defaults -> project config -> runtime override."""
        from butler.config.settings import settings
        base = settings.get_model_config(role)
        project_cfg = self.models.get(role)
        merged = base.merge_with(project_cfg)
        merged = merged.merge_with(runtime_override)
        return merged

    def set_model(self, role: str, config: ModelConfig) -> None:
        self.models[role] = config
        self.save()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "type": self.type,
            "description": self.description,
            "status": self.status,
            "workspace": str(self.workspace),
        }
        if self.models:
            d["models"] = {k: v.to_dict() for k, v in self.models.items() if not v.is_empty()}
        if self.workflows:
            d["workflows"] = self.workflows
        if self.tools:
            d["tools"] = self.tools
        return d

    def save(self) -> None:
        self.workspace.mkdir(parents=True, exist_ok=True)
        config_path = self.workspace / "project.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(self.to_dict(), f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def get_full_status(self) -> dict[str, Any]:
        result = self.to_dict()
        models_display = {}
        for role in ("dev_agent", "content_agent", "review_agent"):
            resolved = self.resolve_model(role)
            if not resolved.is_empty():
                models_display[role] = f"{resolved.provider}:{resolved.model}"
        if models_display:
            result["effective_models"] = models_display

        state = ProjectState(self.workspace)
        wf_state = state.read_workflow_state()
        if wf_state:
            result["workflow_state"] = {
                "current_phase": wf_state.get("current_phase", ""),
                "current_step": wf_state.get("current_step", ""),
                "project_name": wf_state.get("project_name", ""),
                "version": wf_state.get("version", ""),
                "last_updated": wf_state.get("last_updated", ""),
            }
        return result


class ProjectManager:
    """Manages project registry and lifecycle."""

    def __init__(self, projects_dir: Path):
        self.projects_dir = projects_dir
        self._projects: dict[str, Project] = {}
        self.current_project: str = ""
        self._on_switch_callbacks: list = []
        self._scan_projects()

    def _scan_projects(self) -> None:
        if not self.projects_dir.exists():
            self.projects_dir.mkdir(parents=True, exist_ok=True)
            return
        for item in self.projects_dir.iterdir():
            if item.is_dir():
                config = item / "project.yaml"
                if config.exists():
                    try:
                        proj = Project.from_yaml(config)
                        self._projects[proj.name] = proj
                        logger.info(f"Loaded project: {proj.name}")
                    except Exception as e:
                        logger.warning(f"Failed to load project from {config}: {e}")

    def on_switch(self, callback) -> None:
        self._on_switch_callbacks.append(callback)

    def list_projects(self) -> list[Project]:
        return list(self._projects.values())

    def get_project(self, name: str) -> Project | None:
        return self._projects.get(name)

    def switch_project(self, name: str) -> bool:
        matched = None
        if name in self._projects:
            matched = name
        else:
            for proj_name in self._projects:
                if name.lower() in proj_name.lower():
                    matched = proj_name
                    break

        if matched is None:
            return False

        old_project = self.current_project
        self.current_project = matched
        for cb in self._on_switch_callbacks:
            try:
                cb(old_project, matched)
            except Exception as e:
                logger.warning(f"Switch callback error: {e}")
        return True

    def create_project(self, name: str, proj_type: str, description: str) -> bool:
        if name in self._projects:
            return False
        workspace = self.projects_dir / name
        proj = Project(
            name=name,
            type=proj_type,
            description=description,
            workspace=workspace,
            tools=["read_file", "write_file", "edit_file", "search_code", "run_shell", "list_directory"],
        )
        proj.save()
        self._projects[name] = proj
        return True

    def get_current(self) -> Project | None:
        if self.current_project:
            return self._projects.get(self.current_project)
        return None

    def refresh(self) -> None:
        self._projects.clear()
        self._scan_projects()


_project_manager: ProjectManager | None = None


class _ProjectManagerProxy:
    """Lazy proxy so imports work before settings are loaded."""

    def _get(self) -> ProjectManager:
        global _project_manager
        if _project_manager is None:
            from butler.config.settings import settings
            _project_manager = ProjectManager(settings.projects_dir)
        return _project_manager

    def __getattr__(self, name: str) -> Any:
        return getattr(self._get(), name)


project_manager: ProjectManager = _ProjectManagerProxy()  # type: ignore[assignment]
