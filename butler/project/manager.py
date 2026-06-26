"""Registry of Butler projects under the workspace ``projects/`` tree."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Callable

from butler.config import get_butler_settings
from butler.project.model import Project
from butler.session.keys import chat_id_from_session_key, project_from_session_key

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
        import threading

        self._lock = threading.RLock()
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
        """Match display name, slug (folder), case-insensitive, or unique substring."""
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
        by_slug = self._resolve_by_workspace_slug(raw)
        if by_slug is not None:
            return by_slug
        return None

    def _resolve_by_workspace_slug(self, raw: str) -> str | None:
        """Map ``projects/<slug>`` folder name to ``project.yaml`` display name."""
        lower = str(raw or "").strip().lower()
        if not lower:
            return None
        matches: list[str] = []
        for proj in self._projects.values():
            try:
                slug = proj.workspace.name.lower()
            except (OSError, ValueError, TypeError):
                continue
            if slug == lower:
                matches.append(proj.name)
        if len(matches) == 1:
            return matches[0]
        return None

    def suggest_project_names(self, query: str, *, limit: int = 3) -> list[str]:
        """Did-you-mean hints when ``/切换`` fails (slug / display name)."""
        q = str(query or "").strip().lower()
        if not q or limit <= 0:
            return []
        scored: list[tuple[int, str]] = []
        for proj in self._projects.values():
            name = proj.name
            try:
                slug = proj.workspace.name.lower()
            except (OSError, ValueError, TypeError):
                slug = ""
            score = 0
            if q == slug:
                score = 100
            elif slug and (q in slug or slug in q):
                score = 85
            elif q in name.lower():
                score = 70
            elif name.lower() in q:
                score = 60
            if score:
                scored.append((score, name))
        scored.sort(key=lambda x: (-x[0], x[1]))
        out: list[str] = []
        seen: set[str] = set()
        for _, name in scored:
            if name in seen:
                continue
            seen.add(name)
            out.append(name)
            if len(out) >= limit:
                break
        return out

    def switch_project(self, name: str) -> bool:
        matched = self.resolve_project_name(name)
        if matched is None:
            return False

        with self._lock:
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
        with self._lock:
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
        if not key:
            try:
                from butler.execution_context import get_current_session_key

                key = str(get_current_session_key() or "").strip()
            except Exception:
                key = ""
        if key and "::delegate::" in key:
            parent_key = key.split("::delegate::", 1)[0].strip()
            if parent_key and parent_key != key:
                inherited = self.resolve_active_project_name(session_key=parent_key)
                if inherited:
                    return inherited
        if key:
            from_session = project_from_session_key(key)
            if from_session and from_session in self._projects:
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
        with self._lock:
            if name:
                return self._projects.get(name)
        return None

    # ---------------------------------------------------------------- lifecycle
    def create_project(
        self,
        slug: str,
        proj_type: str = "software",
        description: str = "",
        *,
        display_name: str = "",
        pack: str = "",
        template: str = "",
        with_runtime: bool = True,
    ) -> Project | None:
        from butler.project.archetypes import (
            ensure_experiment_skeleton,
            ensure_memory_skeleton,
            ensure_runtime_jobs_skeleton,
            load_template,
            validate_slug,
            write_project_yaml,
        )

        ok, err = validate_slug(slug)
        if not ok:
            raise ValueError(err)

        workspace = self.projects_dir / slug
        if workspace.exists() and (workspace / "project.yaml").is_file():
            return None
        if any(p.workspace == workspace.resolve() for p in self._projects.values()):
            return None

        template_id = (template or pack or "software-default").strip()
        if template_id in ("software", "content"):
            template_id = "software-default"
        data = load_template(template_id)
        show_name = (display_name or data.get("name") or slug).strip()
        if show_name in self._projects:
            return None

        data["name"] = show_name
        if description:
            data["description"] = description
        if proj_type:
            data["type"] = proj_type
        if pack:
            data["pack"] = pack
        data.setdefault("lifecycle", "active")
        if pack == "novel-factory" and data.get("lead") is None:
            data["lead"] = True

        workspace.mkdir(parents=True, exist_ok=True)
        write_project_yaml(workspace, data, merge_existing=False)
        ensure_memory_skeleton(workspace)
        if with_runtime:
            ensure_runtime_jobs_skeleton(workspace, show_name, template_id)
        ensure_experiment_skeleton(workspace, template_id=template_id)
        self.refresh()
        proj = Project.from_yaml(workspace / "project.yaml")
        self._projects[proj.name] = proj
        return proj

    def register_workspace(
        self,
        path: Path,
        *,
        display_name: str = "",
        pack: str = "",
        template: str = "software-default",
        merge_existing: bool = True,
        with_runtime: bool = True,
    ) -> Project:
        from butler.project.archetypes import (
            ensure_experiment_skeleton,
            ensure_memory_skeleton,
            ensure_runtime_jobs_skeleton,
            load_template,
            write_project_yaml,
        )

        ws = path.expanduser().resolve()
        if not ws.is_dir():
            raise ValueError(f"不是目录: {ws}")

        cfg = ws / "project.yaml"
        if cfg.is_file():
            proj = Project.from_yaml(cfg)
            if merge_existing and (pack or display_name):
                if pack and not proj.pack:
                    proj.pack = pack
                if display_name and proj.name != display_name:
                    proj.name = display_name
                proj.save()
            ensure_memory_skeleton(ws)
            if with_runtime:
                tid = (template or pack or proj.pack or "software-default").strip()
                ensure_runtime_jobs_skeleton(ws, proj.name, tid)
            ensure_experiment_skeleton(ws, template_id=(template or pack or proj.pack or ""))
            self.refresh()
            return Project.from_yaml(ws / "project.yaml")

        template_id = (template or pack or "software-default").strip()
        data = load_template(template_id)
        data["name"] = (display_name or ws.name).strip()
        if pack:
            data["pack"] = pack
        if pack == "novel-factory" and data.get("lead") is None:
            data["lead"] = True
        write_project_yaml(ws, data, merge_existing=False)
        ensure_memory_skeleton(ws)
        if with_runtime:
            ensure_runtime_jobs_skeleton(ws, data["name"], template_id)
        ensure_experiment_skeleton(ws, template_id=template_id)
        self.refresh()
        return Project.from_yaml(ws / "project.yaml")

    def refresh(self) -> None:
        self._scan_projects()


def get_project_manager() -> ProjectManager:
    """Shared ``ProjectManager`` singleton."""
    return ProjectManager()


__all__ = ["ProjectManager", "get_project_manager"]
