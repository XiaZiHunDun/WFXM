"""System prompt assembly for ButlerOrchestrator (ENG-12)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from butler.orchestrator import ButlerOrchestrator

from butler.orchestrator import memory_bridge
from butler.orchestrator.templates import (
    format_project_list,
    format_skill_summaries,
    lead_template_path,
    read_template_cached,
    template_path,
)

logger = logging.getLogger(__name__)

_MEMORY_OFFLINE_APPENDIX = (
    "\n\n## 记忆子系统离线 (memory offline)\n"
    "本次会话无法 recall 历史上下文,所有"
    " recall 类工具将返回空结果。"
    "请主动告知用户\"本次对话无历史记忆\","
    "避免产生已记住对方偏好的错觉。"
)


def system_prompt_placeholders(
    orch: ButlerOrchestrator,
    *,
    for_role: str = "default",
) -> dict[str, str]:
    template = template_path()
    body = read_template_cached(template)
    if not body:
        if not template.exists():
            logger.warning("Butler system template missing at %s", template)

    current = orch.project_manager.current_project or "(未选择)"
    project_list = format_project_list(orch._settings)

    from butler.model_resolve import resolve_effective_model

    proj = orch.project_manager.get_current()
    em = resolve_effective_model("butler", project=proj, settings=orch._settings)
    mc = em.config
    prov = mc.provider or orch._settings.default_provider or ""
    parts_model = [
        f"- Provider: `{prov or 'unset'}`",
        f"- Model: `{mc.model or 'unset'}`",
        f"- Sources: `{', '.join(em.sources)}`",
    ]
    if mc.temperature is not None:
        parts_model.append(f"- Temperature: `{mc.temperature}`")
    if mc.max_tokens is not None:
        parts_model.append(f"- Max tokens: `{mc.max_tokens}`")
    model_block = "\n".join(parts_model)

    skills_block = "(技能管理器不可用)"
    if orch._skill_manager is not None:
        skills_block = format_skill_summaries(orch._skill_manager.list_skills())

    memory_ctx = memory_bridge.build_memory_context(orch, for_role=for_role)

    from butler.workflows.loader import format_workflows_for_prompt

    workflows_block = format_workflows_for_prompt(orch.project_manager.get_current())

    return {
        "template_body": body,
        "butler_name": orch._settings.butler_name,
        "owner_name": orch._settings.owner_name,
        "current_project": current,
        "project_list": project_list,
        "memory_context": memory_ctx,
        "butler_model": model_block,
        "skill_summaries": skills_block,
        "workflows_block": workflows_block,
        "model_block": model_block,
    }


def build_dynamic_system_reminder(
    orch: ButlerOrchestrator,
    *,
    for_role: str = "default",
) -> str:
    """Dynamic context injected into the user turn when static system mode is on."""
    try:
        from butler.core.system_reminder import wrap_system_reminder
    except Exception as exc:
        logger.debug("system_reminder import skipped: %s", exc)
        return ""
    ph = system_prompt_placeholders(orch, for_role=for_role)
    chunks = [
        "## 记忆与上下文\n" + (ph.get("memory_context") or "(无)"),
        "## 可用技能概要\n" + ph.get("skill_summaries", ""),
        "## 项目工作流\n" + ph.get("workflows_block", ""),
    ]
    if orch.memory_offline:
        chunks.append(_MEMORY_OFFLINE_APPENDIX.lstrip("\n"))
    body = "\n\n".join(c for c in chunks if c and str(c).strip())
    return cast(str, wrap_system_reminder(body))


def build_static_system_prompt(orch: ButlerOrchestrator) -> str:
    """System prompt without dynamic memory (paired with build_dynamic_system_reminder)."""
    ph = system_prompt_placeholders(orch, for_role="default")
    body = ph.get("template_body") or ""
    placeholders = {
        "butler_name": ph["butler_name"],
        "owner_name": ph["owner_name"],
        "current_project": ph["current_project"],
        "project_list": ph["project_list"],
        "memory_context": "(见本轮 system-reminder)",
        "butler_model": ph["butler_model"],
        "skill_summaries": "(见本轮 system-reminder)",
    }
    rendered = body
    for k, v in placeholders.items():
        rendered = rendered.replace("{" + k + "}", v)
    appendix = (
        "\n\n## Butler 模型\n"
        f"{ph['model_block']}\n\n"
        "## 可用技能概要\n"
        "(见本轮 system-reminder)\n\n"
        "## 项目工作流\n"
        "(见本轮 system-reminder)"
    )
    return rendered.rstrip() + appendix


def resolve_system_prompt(
    orch: ButlerOrchestrator,
    *,
    role: str = "butler",
    session_key: str = "",
) -> tuple[str, str | None]:
    """Return (system_prompt, optional user-side reminder)."""
    if role == "lead":
        return build_lead_system_prompt(orch, session_key=session_key), None
    from butler.core.prompt_renderer import render_orchestrator_turn

    return cast(tuple[str, str | None], render_orchestrator_turn(orch, for_role=role))


def assemble_default_system_prompt(
    orch: ButlerOrchestrator,
    *,
    for_role: str = "default",
) -> str:
    ph = system_prompt_placeholders(orch, for_role=for_role)
    body = ph.get("template_body") or ""
    placeholders = {
        "butler_name": ph["butler_name"],
        "owner_name": ph["owner_name"],
        "current_project": ph["current_project"],
        "project_list": ph["project_list"],
        "memory_context": ph["memory_context"],
        "butler_model": ph["butler_model"],
        "skill_summaries": ph["skill_summaries"],
    }
    rendered = body
    for k, v in placeholders.items():
        rendered = rendered.replace("{" + k + "}", v)
    offline_appendix = _MEMORY_OFFLINE_APPENDIX if orch.memory_offline else ""
    appendix = (
        "\n\n## Butler 模型\n"
        f"{ph['model_block']}\n\n"
        "## 可用技能概要\n"
        f"{ph['skill_summaries']}\n\n"
        "## 项目工作流\n"
        f"{ph['workflows_block']}"
    ) + offline_appendix
    return rendered.rstrip() + appendix


def build_system_prompt(orch: ButlerOrchestrator) -> str:
    try:
        from butler.core.harness_flags import static_system_reminder_enabled

        if static_system_reminder_enabled():
            return build_static_system_prompt(orch)
    except Exception as exc:
        logger.debug("Static system prompt check skipped: %s", exc)
    return assemble_default_system_prompt(orch, for_role="default")


def build_lead_system_prompt(
    orch: ButlerOrchestrator,
    *,
    session_key: str = "",
) -> str:
    """System prompt for project Lead gateway loop (phase 2)."""
    from butler.agent_profiles import get_profile

    path = lead_template_path()
    body = read_template_cached(path)
    if not body:
        if not path.exists():
            logger.warning("Lead system template missing at %s", path)
        prof = get_profile("lead")
        body = prof.system_prompt if prof else ""

    current = orch.project_manager.resolve_active_project_name(
        session_key=session_key,
    ) or orch.project_manager.current_project or "(未选择)"
    memory_ctx = memory_bridge.build_memory_context(orch, for_role="lead")
    from butler.workflows.loader import format_workflows_for_prompt

    workflows_block = format_workflows_for_prompt(
        orch.project_manager.get_current(session_key=session_key or "")
    )
    proj = orch.project_manager.get_current(session_key=session_key or "")
    from butler.project.meta import lifecycle_operating_hint

    lifecycle_block = lifecycle_operating_hint(proj)

    placeholders = {
        "current_project": current,
        "memory_context": memory_ctx or "(无)",
        "workflows_block": workflows_block or "(无)",
        "lifecycle_block": lifecycle_block or "",
    }
    rendered = body
    for k, v in placeholders.items():
        rendered = rendered.replace("{" + k + "}", v)
    if lifecycle_block and "{lifecycle_block}" not in body:
        rendered = rendered.rstrip() + "\n\n" + lifecycle_block
    profile = get_profile("lead")
    if profile:
        from butler.agent_profiles import get_model_aware_prompt_extra

        mc = orch._model_credentials("butler")
        prov = mc.get("provider") or ""
        extra = get_model_aware_prompt_extra(str(prov))
        if extra:
            rendered += "\n\n" + extra
    return cast(str, rendered.rstrip())


__all__ = [
    "assemble_default_system_prompt",
    "build_dynamic_system_reminder",
    "build_lead_system_prompt",
    "build_static_system_prompt",
    "build_system_prompt",
    "resolve_system_prompt",
    "system_prompt_placeholders",
]
