"""Project manager best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from butler.core.best_effort import safe_best_effort
from butler.project.model import Project

logger = logging.getLogger(__name__)

SwitchCallback = Callable[[str, str], None]


def load_project_yaml_safe(config: Path) -> Project | None:
    def _run() -> Project:
        return Project.from_yaml(config)

    result = safe_best_effort(_run, label="project_manager.load_yaml", default=None)
    return result if isinstance(result, Project) else None


def invoke_switch_callbacks_safe(
    callbacks: list[SwitchCallback],
    old: str,
    matched: str,
) -> None:
    for cb in callbacks:
        def _run(callback: SwitchCallback = cb) -> None:
            callback(old, matched)

        safe_best_effort(_run, label="project_manager.switch_callback", default=None)


def current_session_key_safe() -> str:
    def _run() -> str:
        from butler.execution_context import get_current_session_key

        return str(get_current_session_key() or "").strip()

    result = safe_best_effort(_run, label="project_manager.session_key", default="")
    return str(result or "")


def chat_project_from_session_key_safe(manager: Any, key: str) -> str:
    def _run() -> str:
        from butler.session.keys import chat_id_from_session_key

        return str(
            manager.get_project_name_for_chat(
                platform=key.split(":", 1)[0],
                chat_id=chat_id_from_session_key(key),
            )
            or ""
        )

    result = safe_best_effort(_run, label="project_manager.chat_project", default="")
    return str(result or "")
