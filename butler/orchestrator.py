"""Butler Orchestrator — bridges Butler product layer with the Agent Loop.

Provides:
- Butler-scoped system prompt injection (project context, memory, model config)
- LLMClient and AgentLoop factory methods for butler and project agents
- Report collection from delegated tasks
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.config import ButlerSettings, get_butler_settings
from butler.memory import ButlerMemory, ProjectMemory
from butler.memory.facade import ButlerMemoryService
from butler.project_manager import get_project_manager
from butler.skills.manager import SkillManager
from butler.skills.router import SkillRouter

import butler.workflows  # noqa: F401 — register workflow hooks

logger = logging.getLogger(__name__)

_ROLE_ALIASES: dict[str, str] = {
    "dev": "dev_agent",
    "content": "content_agent",
    "review": "review_agent",
}


def _normalize_butler_role(role: str) -> str:
    key = (role or "").strip().lower()
    return _ROLE_ALIASES.get(key, role)


def _template_path() -> Path:
    return Path(__file__).resolve().parent / "prompts" / "butler_system.md"


def _lead_template_path() -> Path:
    return Path(__file__).resolve().parent / "prompts" / "lingwen_lead_system.md"


def _format_project_list(settings: ButlerSettings) -> str:
    pm = get_project_manager()
    names = sorted(p.name for p in pm.list_projects())
    if not names:
        return f"(无 — 在 {settings.projects_dir} 下创建 project.yaml)"
    return ", ".join(names)


def _format_skill_summaries(skills: list[dict[str, Any]], max_items: int = 20) -> str:
    if not skills:
        return "(尚无技能文件 — 可在 ~/.butler/tenants/<tenant>/skills 或项目 `.butler/skills` 中添加)"
    lines: list[str] = []
    for sk in skills[:max_items]:
        name = sk.get("name", "")
        desc = (sk.get("description") or "").strip()
        triggers = sk.get("triggers") or []
        trig = ", ".join(str(t) for t in triggers[:5])
        if trig:
            lines.append(f"- **{name}**: {desc} (triggers: {trig})")
        else:
            lines.append(f"- **{name}**: {desc}")
    if len(skills) > max_items:
        lines.append(f"... 另有 {len(skills) - max_items} 条技能未列出")
    return "\n".join(lines)


def _combined_skill_manager(
    settings: ButlerSettings,
    project_workspace: Path | None,
    *,
    tenant_id: str,
) -> SkillManager:
    """Project-local skills override tenant-global skills with the same name."""
    from butler.tenant import tenant_skills_dir

    global_dir = tenant_skills_dir(settings.butler_home, tenant_id)
    global_dir.mkdir(parents=True, exist_ok=True)
    if project_workspace is None:
        return SkillManager(skills_dir=global_dir, global_skills_dir=None)
    proj_skills = Path(project_workspace).expanduser().resolve() / ".butler" / "skills"
    proj_skills.mkdir(parents=True, exist_ok=True)
    return SkillManager(skills_dir=proj_skills, global_skills_dir=global_dir)


class ButlerOrchestrator:
    """Bridge Butler configuration/memories into AgentLoop instances."""

    def __init__(self, user_id: str = "owner", channel: str = "cli") -> None:
        self.user_id = user_id
        self.channel = channel
        self._settings = get_butler_settings()
        self._memory_by_tenant: dict[str, ButlerMemory] = {}
        self.project_manager = get_project_manager()
        self._project_memory: ProjectMemory | None = None
        self._skill_router: SkillRouter | None = None
        self._skill_manager: SkillManager | None = None
        self.memory_provider = None
        self._reload_project_memory()
        self._rebuild_skill_router()
        self._initialize_memory_provider()
        self.project_manager.on_switch(self._pm_switch)

    def _pm_switch(self, old_project: str, new_project: str) -> None:
        self.on_project_switch(old_project, new_project)

    def _reload_project_memory(self) -> None:
        proj = self.project_manager.get_current()
        if proj is None:
            self._project_memory = None
        else:
            self._project_memory = ProjectMemory(proj.workspace)
            try:
                self._project_memory.refresh_facts()
            except Exception as exc:
                logger.debug("Project facts refresh skipped: %s", exc)

    @property
    def butler_memory(self) -> ButlerMemory:
        from butler.tenant import resolve_tenant_for_project

        tid = resolve_tenant_for_project(
            self.project_manager.get_current(),
            self._settings,
        )
        mem = self._memory_by_tenant.get(tid)
        if mem is None:
            mem = ButlerMemory(self._settings.butler_home, tenant_id=tid)
            self._memory_by_tenant[tid] = mem
        return mem

    def _rebuild_skill_router(self) -> None:
        from butler.tenant import resolve_tenant_for_project

        tid = resolve_tenant_for_project(
            self.project_manager.get_current(),
            self._settings,
        )
        mgr = _combined_skill_manager(
            self._settings,
            self._project_workspace(),
            tenant_id=tid,
        )
        self._skill_manager = mgr
        payloads = mgr.list_skills()
        self._skill_router = SkillRouter(
            payloads,
            content_loader=mgr.get_skill,
            batch_content_loader=mgr.get_skills,
        )

    def _initialize_memory_provider(self) -> None:
        try:
            provider = ButlerMemoryService()
            provider.link_orchestrator(self)
            provider.initialize(
                session_id=f"{self.channel}:{self.user_id}",
                user_id=self.user_id,
            )
            self.memory_provider = provider
        except Exception as exc:
            logger.warning("Butler memory provider unavailable: %s", exc)
            self.memory_provider = None

    def _refresh_memory_provider_for_project_switch(self) -> None:
        provider = getattr(self, "memory_provider", None)
        if provider is None:
            return
        try:
            if hasattr(provider, "_turn_buffer"):
                provider._turn_buffer.clear()
            if hasattr(provider, "_reload_butler_global"):
                provider._reload_butler_global()
            if hasattr(provider, "_reload_project_branch"):
                provider._reload_project_branch()
        except Exception as exc:
            logger.debug("Butler memory provider refresh skipped: %s", exc)

    def _project_workspace(self) -> Path | None:
        p = self.project_manager.get_current()
        return p.workspace if p else None

    def _model_credentials(self, role: str) -> dict[str, Any]:
        from butler.model_resolve import model_config_to_credentials, resolve_effective_model

        role = _normalize_butler_role(role)
        project = self.project_manager.get_current()
        em = resolve_effective_model(role, project=project, settings=self._settings)
        return model_config_to_credentials(em.config, settings=self._settings)

    def build_memory_context(self, *, for_role: str = "default") -> str:
        current = self.project_manager.current_project or ""
        chunks: list[str] = []

        bm = self.butler_memory.get_system_context(current)
        chunks.append(bm)

        if self._project_memory is not None:
            pm_txt = self._project_memory.get_context_for_agent(for_role)
            chunks.append(f"## 当前项目记忆\n{pm_txt}")

        proj = self.project_manager.get_current()
        if proj is not None:
            try:
                from butler.core.design_md_sections import build_design_context_block

                design_block = build_design_context_block(
                    Path(proj.workspace),
                    design_preset=str(getattr(proj, "design_preset", "") or ""),
                )
                if design_block.strip():
                    chunks.append(design_block.strip())
            except Exception as exc:
                logger.debug("DESIGN context inject skipped: %s", exc)

        try:
            from pathlib import Path

            from butler.experiments.outcomes import format_context_for_prompt

            if proj is not None:
                outcome_block = format_context_for_prompt(
                    Path(proj.workspace),
                    project=str(proj.name or current or ""),
                )
                if outcome_block.strip():
                    chunks.append(outcome_block.strip())
        except Exception as exc:
            logger.debug("Outcome context inject skipped: %s", exc)

        return "\n\n".join(c for c in chunks if c and str(c).strip())

    def _system_prompt_placeholders(self, *, for_role: str = "default") -> dict[str, str]:
        template = _template_path()
        try:
            body = template.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Butler system template missing at %s", template)
            body = ""

        current = self.project_manager.current_project or "(未选择)"
        project_list = _format_project_list(self._settings)

        from butler.model_resolve import resolve_effective_model

        proj = self.project_manager.get_current()
        em = resolve_effective_model("butler", project=proj, settings=self._settings)
        mc = em.config
        prov = mc.provider or self._settings.default_provider or ""
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
        if self._skill_manager is not None:
            skills_block = _format_skill_summaries(self._skill_manager.list_skills())

        memory_ctx = self.build_memory_context(for_role=for_role)

        from butler.workflows.loader import format_workflows_for_prompt

        workflows_block = format_workflows_for_prompt(self.project_manager.get_current())

        return {
            "template_body": body,
            "butler_name": self._settings.butler_name,
            "owner_name": self._settings.owner_name,
            "current_project": current,
            "project_list": project_list,
            "memory_context": memory_ctx,
            "butler_model": model_block,
            "skill_summaries": skills_block,
            "workflows_block": workflows_block,
            "model_block": model_block,
        }

    def build_dynamic_system_reminder(self, *, for_role: str = "default") -> str:
        """Dynamic context injected into the user turn when static system mode is on."""
        try:
            from butler.core.system_reminder import wrap_system_reminder
        except Exception:
            return ""
        ph = self._system_prompt_placeholders(for_role=for_role)
        chunks = [
            "## 记忆与上下文\n" + (ph.get("memory_context") or "(无)"),
            "## 可用技能概要\n" + ph.get("skill_summaries", ""),
            "## 项目工作流\n" + ph.get("workflows_block", ""),
        ]
        body = "\n\n".join(c for c in chunks if c and str(c).strip())
        return wrap_system_reminder(body)

    def build_static_system_prompt(self) -> str:
        """System prompt without dynamic memory (paired with build_dynamic_system_reminder)."""
        ph = self._system_prompt_placeholders(for_role="default")
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
        self,
        *,
        role: str = "butler",
        session_key: str = "",
    ) -> tuple[str, str | None]:
        """Return (system_prompt, optional user-side reminder)."""
        if role == "lead":
            return self.build_lead_system_prompt(session_key=session_key), None
        from butler.core.prompt_renderer import render_orchestrator_turn

        return render_orchestrator_turn(self, for_role=role)

    def _assemble_default_system_prompt(self, *, for_role: str = "default") -> str:
        ph = self._system_prompt_placeholders(for_role=for_role)
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
        appendix = (
            "\n\n## Butler 模型\n"
            f"{ph['model_block']}\n\n"
            "## 可用技能概要\n"
            f"{ph['skill_summaries']}\n\n"
            "## 项目工作流\n"
            f"{ph['workflows_block']}"
        )
        return rendered.rstrip() + appendix

    def build_system_prompt(self) -> str:
        try:
            from butler.core.harness_flags import static_system_reminder_enabled

            if static_system_reminder_enabled():
                return self.build_static_system_prompt()
        except Exception:
            pass
        return self._assemble_default_system_prompt(for_role="default")

    def build_lead_system_prompt(self, *, session_key: str = "") -> str:
        """System prompt for project Lead gateway loop (phase 2)."""
        from butler.agent_profiles import get_profile

        path = _lead_template_path()
        try:
            body = path.read_text(encoding="utf-8")
        except OSError:
            logger.warning("Lead system template missing at %s", path)
            prof = get_profile("lead")
            body = prof.system_prompt if prof else ""

        current = self.project_manager.resolve_active_project_name(
            session_key=session_key,
        ) or self.project_manager.current_project or "(未选择)"
        memory_ctx = self.build_memory_context(for_role="lead")
        from butler.workflows.loader import format_workflows_for_prompt

        workflows_block = format_workflows_for_prompt(
            self.project_manager.get_current(session_key=session_key or "")
        )
        proj = self.project_manager.get_current(session_key=session_key or "")
        from butler.project_meta import lifecycle_operating_hint

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

            mc = self._model_credentials("butler")
            prov = mc.get("provider") or ""
            extra = get_model_aware_prompt_extra(str(prov))
            if extra:
                rendered += "\n\n" + extra
        return rendered.rstrip()

    def get_agent_kwargs(self) -> dict[str, Any]:
        """Return kwargs dict (kept for backward compat)."""
        mc = self._model_credentials("butler")
        return {
            "model": mc.get("model", ""),
            "provider": mc.get("provider"),
            "base_url": mc.get("base_url") or "",
            "api_key": mc.get("api_key") or "",
            "max_tokens": mc.get("max_tokens"),
            "user_id": self.user_id,
            "platform": self.channel,
            "ephemeral_system_prompt": self.resolve_system_prompt(role="butler")[0],
        }

    def create_llm_client(self, role: str = "butler") -> "LLMClient":
        """Create an LLMClient for the given role."""
        from butler.transport.llm_client import LLMClient
        mc = self._model_credentials(role)
        return LLMClient(
            provider=mc.get("provider") or "",
            model=mc.get("model") or "",
            api_key=mc.get("api_key") or None,
            base_url=mc.get("base_url") or None,
            max_tokens=mc.get("max_tokens"),
        )

    def create_agent_loop(
        self,
        role: str = "butler",
        *,
        tools: list[dict] | None = None,
        tool_dispatcher: Any = None,
        callbacks: Any = None,
        session_key: str = "",
    ) -> "AgentLoop":
        """Create a fully configured AgentLoop for the given role."""
        from butler.config import ModelConfig
        from butler.core.agent_loop import AgentLoop, LoopConfig
        from butler.transport.fallback import build_fallback_chain
        from butler.transport.model_context import infer_context_length

        llm_role = "butler" if role in ("lead", "plan") else role
        client = self.create_llm_client(llm_role)
        mc = self._model_credentials(llm_role)
        primary = ModelConfig(provider=mc.get("provider") or "", model=mc.get("model") or "")
        fallback_chain = build_fallback_chain(primary)

        sk = str(session_key or "").strip()
        try:
            proj = self.project_manager.get_current(session_key=sk)
            from butler.project_plugins import apply_project_plugins

            apply_project_plugins(proj)
        except Exception:
            pass

        user_reminder: str | None = None
        if role == "butler":
            system_prompt, user_reminder = self.resolve_system_prompt(role="butler", session_key=sk)
        elif role == "lead":
            system_prompt = self.build_lead_system_prompt(session_key=sk)
        elif role == "plan":
            system_prompt, user_reminder = self.resolve_system_prompt(role="plan", session_key=sk)
            from butler.plan_mode import load_plan_mode_system_appendix

            system_prompt = system_prompt.rstrip() + "\n\n" + load_plan_mode_system_appendix()
        else:
            system_prompt = ""
            from butler.agent_profiles import get_profile
            profile = get_profile(role.replace("_agent", ""))
            if profile:
                system_prompt = profile.system_prompt
                from butler.agent_profiles import get_model_aware_prompt_extra
                extra = get_model_aware_prompt_extra(client.provider_name or "")
                if extra:
                    system_prompt += "\n\n" + extra

        if sk and role != "plan":
            try:
                from butler.plan_mode import is_plan_mode, load_plan_mode_system_appendix

                if is_plan_mode(sk):
                    system_prompt = system_prompt.rstrip() + "\n\n" + load_plan_mode_system_appendix()
            except Exception:
                pass

        return AgentLoop(
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

    def create_project_agent_loop(
        self,
        role: str = "dev",
        *,
        tools: list[dict] | None = None,
        tool_dispatcher: Any = None,
        callbacks: Any = None,
    ) -> "AgentLoop":
        """Create an AgentLoop configured for a project-level agent."""
        from butler.core.agent_loop import AgentLoop, LoopConfig
        from butler.agent_profiles import get_profile, get_model_aware_prompt_extra

        normalized_role = _normalize_butler_role(role)
        kw = self.get_project_agent_kwargs(role)

        from butler.transport.llm_client import LLMClient
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

        from butler.config import ModelConfig
        from butler.transport.fallback import build_fallback_chain
        from butler.transport.model_context import infer_context_length

        primary = ModelConfig(
            provider=kw.get("provider") or "",
            model=kw.get("model") or "",
            context_length=kw.get("context_length"),
        )
        fallback_chain = build_fallback_chain(primary)

        return AgentLoop(
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

    def get_project_agent_kwargs(self, role: str) -> dict[str, Any]:
        """Return kwargs for project-level agents (dev/content/review)."""
        r = _normalize_butler_role(role)
        proj = self.project_manager.get_current()
        if proj is None:
            mcreds = self._model_credentials(r)
            extra_prompt = (
                "## Butler 项目上下文\n"
                "当前未选择 Butler 项目 — 使用全局模型配置。"
            )
        else:
            from butler.model_resolve import model_config_to_credentials, resolve_effective_model

            em = resolve_effective_model(r, project=proj, settings=self._settings)
            mcreds = model_config_to_credentials(em.config, settings=self._settings)

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
            "user_id": self.user_id,
            "platform": self.channel,
            "ephemeral_system_prompt": extra_prompt,
        }

    def on_project_switch(self, old_project: str, new_project: str) -> None:
        logger.debug(
            "Butler project switched: %r -> %r",
            old_project,
            new_project,
        )
        self._reload_project_memory()
        self._rebuild_skill_router()
        self._refresh_memory_provider_for_project_switch()

    def inject_skill_context(
        self,
        task_description: str,
        top_k: int = 3,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> str:
        """Augment ``task_description`` with bodies from :class:`~butler.skills.router.SkillRouter`."""
        if not task_description.strip():
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_matches"] = []
            return task_description
        if self._skill_router is None:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_matches"] = []
            return task_description
        matched = self._skill_router.match(task_description, top_k=top_k)
        if not matched:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_matches"] = []
            return task_description
        if diagnostics is not None:
            diagnostics["skill_matches"] = [str(sk.get("name")) for sk in matched if sk.get("name")]

        sections: list[str] = [
            "## 相关知识（Butler Skill）",
            "",
            "> 以下内容来自与本任务相关的 Butler 技能，仅作上下文参考。",
        ]
        for sk in matched:
            content = str(sk.get("content") or "").strip()
            if not content:
                continue
            name = sk.get("name", "skill")
            score = sk.get("match_score")
            hdr = f"### `{name}`" + (f" (相关性 {score})" if score is not None else "")
            sections.append(hdr)
            sections.append(content)

        if len(sections) == 3:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_empty_matches"] = [str(sk.get("name")) for sk in matched if sk.get("name")]
            return task_description

        sections.append("")
        sections.append(task_description.strip())
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = True
        return "\n".join(sections).strip()


__all__ = ["ButlerOrchestrator"]
