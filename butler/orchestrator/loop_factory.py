"""AgentLoop / LLMClient factory helpers (ENG-12)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop
    from butler.orchestrator import ButlerOrchestrator
    from butler.transport.llm_client import LLMClient

from butler.agent_profiles import get_model_aware_prompt_extra, get_profile
from butler.config import ModelConfig
from butler.core.agent_loop import AgentLoop, LoopConfig
from butler.memory import ProjectMemory
from butler.model_resolve import model_config_to_credentials, resolve_effective_model
from butler.orchestrator.loop_factory_ops import (
    append_plan_mode_appendix_safe,
    apply_project_plugins_safe,
)
from butler.orchestrator.templates import normalize_butler_role
from butler.plan.mode import load_plan_mode_system_appendix
from butler.transport.fallback import build_fallback_chain
from butler.transport.llm_client import LLMClient
from butler.transport.model_context import infer_context_length


def create_llm_client(orch: ButlerOrchestrator, role: str = "butler") -> LLMClient:
    """Create an LLMClient for the given role."""
    mc = orch._model_credentials(role)
    return LLMClient(
        provider=mc.get("provider") or "",
        model=mc.get("model") or "",
        api_key=mc.get("api_key") or None,
        base_url=mc.get("base_url") or None,
        max_tokens=mc.get("max_tokens"),
    )


def get_agent_kwargs(orch: ButlerOrchestrator) -> dict[str, Any]:
    """Return kwargs dict (kept for backward compat)."""
    mc = orch._model_credentials("butler")
    return {
        "model": mc.get("model", ""),
        "provider": mc.get("provider"),
        "base_url": mc.get("base_url") or "",
        "api_key": mc.get("api_key") or "",
        "max_tokens": mc.get("max_tokens"),
        "user_id": orch.user_id,
        "platform": orch.channel,
        "ephemeral_system_prompt": orch.resolve_system_prompt(role="butler")[0],
    }


def get_project_agent_kwargs(orch: ButlerOrchestrator, role: str) -> dict[str, Any]:
    """Return kwargs for project-level agents (dev/content/review)."""
    r = normalize_butler_role(role)
    proj = orch.project_manager.get_current()
    if proj is None:
        mcreds = orch._model_credentials(r)
        extra_prompt = (
            "## Butler 项目上下文\n"
            "当前未选择 Butler 项目 — 使用全局模型配置。"
        )
    else:
        em = resolve_effective_model(r, project=proj, settings=orch._settings)
        mcreds = model_config_to_credentials(em.config, settings=orch._settings)

        proj_mem = ProjectMemory(proj.workspace)
        mem_txt = proj_mem.get_context_for_agent(r)
        extra_prompt = (
            f"## Butler 项目: {proj.name}\n"
            f"{proj.description}\n\n"
            f"工作区路径: `{proj.workspace}`\n\n"
            f"### 项目记忆\n{mem_txt}"
        )

    return {
        "model": mcreds.get("model", ""),
        "provider": mcreds.get("provider"),
        "base_url": mcreds.get("base_url") or "",
        "api_key": mcreds.get("api_key") or "",
        "max_tokens": mcreds.get("max_tokens"),
        "context_length": mcreds.get("context_length"),
        "user_id": orch.user_id,
        "platform": orch.channel,
        "ephemeral_system_prompt": extra_prompt,
    }


def create_agent_loop(
    orch: ButlerOrchestrator,
    role: str = "butler",
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_dispatcher: Any = None,
    callbacks: Any = None,
    session_key: str = "",
) -> AgentLoop:
    """Create a fully configured AgentLoop for the given role."""
    llm_role = "butler" if role in ("lead", "plan") else role
    client = create_llm_client(orch, llm_role)
    mc = orch._model_credentials(llm_role)
    primary = ModelConfig(provider=mc.get("provider") or "", model=mc.get("model") or "")
    fallback_chain = build_fallback_chain(primary)

    sk = str(session_key or "").strip()
    apply_project_plugins_safe(orch, sk)

    if role == "butler":
        system_prompt, _user_reminder = orch.resolve_system_prompt(role="butler", session_key=sk)
    elif role == "lead":
        system_prompt = orch.build_lead_system_prompt(session_key=sk)
    elif role == "plan":
        system_prompt, _user_reminder = orch.resolve_system_prompt(role="plan", session_key=sk)
        system_prompt = system_prompt.rstrip() + "\n\n" + load_plan_mode_system_appendix()
    else:
        system_prompt = ""
        profile = get_profile(role.replace("_agent", ""))
        if profile:
            system_prompt = profile.system_prompt
            extra = get_model_aware_prompt_extra(client.provider_name or "")
            if extra:
                system_prompt += "\n\n" + extra

    if sk and role != "plan":
        system_prompt = append_plan_mode_appendix_safe(sk, system_prompt)

    loop = AgentLoop(
        client=client,
        system_prompt=system_prompt,
        tools=tools or [],
        tool_dispatcher=tool_dispatcher,
        config=LoopConfig(
            fallback_entries=fallback_chain,
            max_context_tokens=infer_context_length(
                provider=mc.get("provider") or "",
                model=mc.get("model") or "",
                configured=mc.get("context_length"),
            ),
        ),
        callbacks=callbacks,
    )
    loop.bind_execution(orch, session_key=sk, loop_role=role)
    return loop


def create_project_agent_loop(
    orch: ButlerOrchestrator,
    role: str = "dev",
    *,
    tools: list[dict[str, Any]] | None = None,
    tool_dispatcher: Any = None,
    callbacks: Any = None,
    session_key: str = "",
) -> AgentLoop:
    """Create an AgentLoop configured for a project-level agent."""
    kw = get_project_agent_kwargs(orch, role)

    client = LLMClient(
        provider=kw.get("provider") or "",
        model=kw.get("model") or "",
        api_key=kw.get("api_key") or None,
        base_url=kw.get("base_url") or None,
        max_tokens=kw.get("max_tokens"),
    )

    profile = get_profile(role)
    system_parts = []
    if profile:
        system_parts.append(profile.system_prompt)
    system_parts.append(kw.get("ephemeral_system_prompt", ""))

    extra = get_model_aware_prompt_extra(client.provider_name or "")
    if extra:
        system_parts.append(extra)

    system_prompt = "\n\n".join(p for p in system_parts if p)

    primary = ModelConfig(
        provider=kw.get("provider") or "",
        model=kw.get("model") or "",
        context_length=kw.get("context_length"),
    )
    fallback_chain = build_fallback_chain(primary)

    loop = AgentLoop(
        client=client,
        system_prompt=system_prompt,
        tools=tools or [],
        tool_dispatcher=tool_dispatcher,
        config=LoopConfig(
            fallback_entries=fallback_chain,
            max_context_tokens=infer_context_length(
                provider=kw.get("provider") or "",
                model=kw.get("model") or "",
                configured=kw.get("context_length"),
            ),
        ),
        callbacks=callbacks,
    )
    loop.bind_execution(orch, session_key=str(session_key or ""), loop_role=role)
    return loop


__all__ = [
    "create_agent_loop",
    "create_llm_client",
    "create_project_agent_loop",
    "get_agent_kwargs",
    "get_project_agent_kwargs",
]
