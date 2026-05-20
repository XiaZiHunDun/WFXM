"""Registry of Butler projects under the workspace ``projects/`` tree."""

from __future__ import annotations

import logging
import os
from typing import Any, Callable

from butler.config import get_butler_settings
from butler.project import Project
from butler.session_keys import chat_id_from_session_key, project_from_session_key

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
        self._default_project: str = os.getenv("BUTLER_DEFAULT_PROJECT", "").strip()
        self._chat_project: dict[str, str] = {}
        self._on_switch_callbacks: list[SwitchCallback] = []
        self._scan_projects()
        if self._default_project and self._default_project in self._projects:
            self.current_project = self._default_project

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

    @staticmethod
    def chat_scope_key(*, platform: str, chat_id: str) -> str:
        plat = str(platform or "unknown").strip() or "unknown"
        cid = str(chat_id or "default").strip() or "default"
        return f"{plat}:{cid}"

    def resolve_project_name(self, name: str) -> str | None:
        """Match a user-provided project name (exact, then unique case-insensitive, then unique substring)."""
        raw = str(name or "").strip()
        if not raw:
            return None
        if raw in self._projects:
            return raw
        lower = raw.lower()
        ci = [p for p in self._projects if p.lower() == lower]
        if len(ci) == 1:
            return ci[0]
        if len(ci) > 1:
            return None
        substr = [p for p in self._projects if lower in p.lower()]
        if len(substr) == 1:
            return substr[0]
        return None

    def switch_project(self, name: str) -> bool:
        matched = self.resolve_project_name(name)
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

    def switch_project_for_chat(self, *, platform: str, chat_id: str, name: str) -> bool:
        """Gateway: bind project choice to ``platform:chat_id`` instead of process-global state."""
        matched = self.resolve_project_name(name)
        if matched is None:
            return False
        scope = self.chat_scope_key(platform=platform, chat_id=chat_id)
        old = self._chat_project.get(scope, "")
        self._chat_project[scope] = matched
        for cb in self._on_switch_callbacks:
            try:
                cb(old, matched)
            except Exception as exc:
                logger.warning("Project switch callback error: %s", exc)
        return True

    def get_project_name_for_chat(self, *, platform: str, chat_id: str) -> str:
        scope = self.chat_scope_key(platform=platform, chat_id=chat_id)
        bound = self._chat_project.get(scope, "").strip()
        if bound:
            return bound
        if self.current_project and self.current_project in self._projects:
            return self.current_project
        if self._default_project in self._projects:
            return self._default_project
        return ""

    def resolve_active_project_name(self, *, session_key: str = "") -> str:
        """Resolve project for CLI (global) or gateway (per-chat map + session key)."""
        key = str(session_key or "").strip()
        if key:
            from_session = project_from_session_key(key)
            if from_session:
                return from_session
            parts = key.split(":", 2)
            if len(parts) >= 2:
                chat_name = self.get_project_name_for_chat(
                    platform=parts[0],
                    chat_id=parts[1],
                )
                if chat_name:
                    return chat_name
        chat_only = ""
        if key:
            try:
                chat_only = self.get_project_name_for_chat(
                    platform=key.split(":", 1)[0],
                    chat_id=chat_id_from_session_key(key),
                )
            except Exception:
                chat_only = ""
        if chat_only:
            return chat_only
        if self.current_project:
            return self.current_project
        if self._default_project in self._projects:
            return self._default_project
        return ""

    # ----------------------------------------------------------------- access
    def list_projects(self) -> list[Project]:
        return list(self._projects.values())

    def get_project(self, name: str) -> Project | None:
        return self._projects.get(name)

    def get_current(self, *, session_key: str = "") -> Project | None:
        name = self.resolve_active_project_name(session_key=session_key)
        if name:
            return self._projects.get(name)
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
