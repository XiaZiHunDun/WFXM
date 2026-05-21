"""Workflow hooks on the Butler gateway hook bus."""

from __future__ import annotations

import logging
from typing import Any

from butler.gateway.hooks import register_hook

logger = logging.getLogger(__name__)
_REGISTERED = False


_LINGWEN_PROJECT_NAMES = frozenset({"灵文1号", "灵文1"})


def _is_lingwen_project(name: str) -> bool:
    return (name or "").strip() in _LINGWEN_PROJECT_NAMES


def _lingwen_lead_ephemeral() -> str:
    return (
        "【灵文厂长模式】你正在统筹灵文1号。回答 phase/step 前必读 "
        "novel-factory/workflow_state.json；在项目内动手一律 "
        "delegate_task（content/dev/review），不要自行 write/edit/terminal。"
        "25 步主流程用 novel-factory 脚本；Butler 短工作流仅 novel-factory / "
        "novel-factory-status。遵循 Skill lingwen-project-lead。"
    )


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
    parts: list[str] = []
    if _is_lingwen_project(new_project) or _is_lingwen_project(
        str(getattr(proj, "name", "") or "")
    ):
        parts.append(_lingwen_lead_ephemeral())
    if names:
        parts.append(f"当前项目已注册工作流: {', '.join(names)}。")
    if not parts:
        return None
    logger.debug(
        "Project switched %r -> %r; workflows=%s lingwen=%s",
        old_project,
        new_project,
        ", ".join(names) if names else "-",
        _is_lingwen_project(new_project),
    )
    return {"context": " ".join(parts)}


def _pre_llm_lingwen_lead(
    *,
    orchestrator: Any | None = None,
    **_: Any,
) -> dict[str, str] | None:
    if orchestrator is None:
        return None
    current = ""
    try:
        current = str(orchestrator.project_manager.current_project or "").strip()
    except Exception:
        return None
    if not _is_lingwen_project(current):
        return None
    return {"context": _lingwen_lead_ephemeral()}


def register_workflow_hooks() -> None:
    global _REGISTERED
    if _REGISTERED:
        return
    register_hook("project_switched", _on_project_switched)
    register_hook("pre_llm_call", _pre_llm_lingwen_lead)
    _REGISTERED = True


__all__ = ["register_workflow_hooks"]
