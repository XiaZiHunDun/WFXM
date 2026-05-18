"""Registry of Butler projects under the workspace ``projects/`` tree."""

from __future__ import annotations

import logging
from typing import Any, Callable

from butler.config import get_butler_settings
from butler.project import Project

logger = logging.getLogger(__name__)

SwitchCallback = Callable[[str, str], None]


class ProjectManager:
    """Scans ``project.yaml`` files and tracks the active Butler project."""

    _instance: ProjectManager | None = None

    def __new__(cls, *_args: Any, **_kwargs: Any) -> ProjectManager:
        if cls._instance is None:
            inst = super().__new__(cls)
            inst._initialized = False  # type: ignore[attr-defined]
            cls._instance = inst
        assert cls._instance is not None
        return cls._instance

    def __init__(self, projects_dir: Any = None) -> None:
        if getattr(self, "_initialized", False):
            return
        self._initialized = True
        settings = get_butler_settings()
        self.projects_dir = (
            projects_dir if projects_dir is not None else settings.projects_dir
        )
        self.projects_dir = self.projects_dir.expanduser().resolve()
        self._projects: dict[str, Project] = {}
        self.current_project: str = ""
        self._on_switch_callbacks: list[SwitchCallback] = []
        self._scan_projects()

    # ------------------------------------------------------------------ scans
    def _scan_projects(self) -> None:
        self._projects.clear()
        if not self.projects_dir.exists():
            self.projects_dir.mkdir(parents=True, exist_ok=True)
            return
        for item in self.projects_dir.iterdir():
            if not item.is_dir():
                continue
            config = item / "project.yaml"
            if not config.exists():
                continue
            try:
                proj = Project.from_yaml(config)
                self._projects[proj.name] = proj
                logger.info("Loaded Butler project %s", proj.name)
            except Exception as exc:
                logger.warning("Failed to load project %s: %s", config, exc)

    # -------------------------------------------------------------- switching
    def on_switch(self, callback: SwitchCallback) -> None:
        self._on_switch_callbacks.append(callback)

    def switch_project(self, name: str) -> bool:
        matched: str | None = None
        if name in self._projects:
            matched = name
        else:
            lower = name.lower()
            for proj_name in self._projects:
                if lower in proj_name.lower():
                    matched = proj_name
                    break

        if matched is None:
            return False

        old = self.current_project
        self.current_project = matched
        for cb in self._on_switch_callbacks:
            try:
                cb(old, matched)
            except Exception as exc:
                logger.warning("Project switch callback error: %s", exc)
        return True

    # ----------------------------------------------------------------- access
    def list_projects(self) -> list[Project]:
        return list(self._projects.values())

    def get_project(self, name: str) -> Project | None:
        return self._projects.get(name)

    def get_current(self) -> Project | None:
        if self.current_project:
            return self._projects.get(self.current_project)
        return None

    # ---------------------------------------------------------------- lifecycle
    def create_project(self, name: str, proj_type: str, description: str) -> Project | None:
        if name in self._projects:
            return None
        workspace = self.projects_dir / name
        proj = Project(
            name=name,
            type=proj_type,
            description=description,
            status="active",
            workspace=workspace,
            tools=[
                "read_file",
                "write_file",
                "edit_file",
                "search_code",
                "run_shell",
                "list_directory",
            ],
        )
        proj.save()
        self._projects[name] = proj
        return proj

    def refresh(self) -> None:
        self._scan_projects()


def get_project_manager() -> ProjectManager:
    """Shared ``ProjectManager`` singleton."""
    return ProjectManager()


__all__ = ["ProjectManager", "get_project_manager"]
