"""Workflow hooks on the Butler gateway hook bus."""

from __future__ import annotations

import logging
from typing import Any

from butler.gateway.hooks import register_hook

logger = logging.getLogger(__name__)
_REGISTERED = False


def _on_project_switched(
    *,
    old_project: str = "",
    new_project: str = "",
    orchestrator: Any | None = None,
    **_: Any,
) -> dict[str, str] | None:
    if orchestrator is None:
        return None
    proj = orchestrator.project_manager.get_current()
    if proj is None:
        return None
    from butler.workflows.loader import list_workflows_for_project

    names = [wf.name for wf in list_workflows_for_project(proj)]
    if not names:
        return None
    logger.debug(
        "Project switched %r -> %r; workflows available: %s",
        old_project,
        new_project,
        ", ".join(names),
    )
    return {"context": f"当前项目已注册工作流: {', '.join(names)}。"}


def register_workflow_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_hook("project_switched", _on_project_switched)
    _REGISTERED = True


__all__ = ["register_workflow_hooks"]
