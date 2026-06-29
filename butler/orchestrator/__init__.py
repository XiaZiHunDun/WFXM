"""Butler Orchestrator — bridges Butler product layer with the Agent Loop.

Provides:
- Butler-scoped system prompt injection (project context, memory, model config)
- LLMClient and AgentLoop factory methods for butler and project agents
- Report collection from delegated tasks
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop
    from butler.transport.llm_client import LLMClient

from butler.config import get_butler_settings
from butler.memory import ButlerMemory, ProjectMemory
from butler.memory.facade import ButlerMemoryService
from butler.orchestrator import loop_factory
from butler.orchestrator.templates import (
    combined_skill_manager,
    format_project_list,
    format_skill_summaries,
    lead_template_path,
    normalize_butler_role,
    read_template_cached,
    template_path,
)
from butler.project.manager import get_project_manager
from butler.skills.router import SkillRouter

import butler.workflows  # noqa: F401 — register workflow hooks

logger = logging.getLogger(__name__)


class ButlerOrchestrator:
    """Bridge Butler configuration/memories into AgentLoop instances."""

    def __init__(self, user_id: str = "owner", channel: str = "cli") -> None:
        self.user_id = user_id
        self.channel = channel
        self._settings = get_butler_settings()
        self._memory_by_tenant: dict[str, ButlerMemory] = {}
        self._memory_lock = threading.Lock()
        self.project_manager = get_project_manager()
        self._project_memory: ProjectMemory | None = None
        self._skill_router: SkillRouter | None = None
        self._skill_manager = None
        self.memory_provider = None
        self.memory_offline: bool = False
        self._memory_init_error: str = ""
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
        with self._memory_lock:
            mem = self._memory_by_tenant.get(tid)
            if mem is None:
                if len(self._memory_by_tenant) >= 64:
                    oldest = next(iter(self._memory_by_tenant))
                    evicted = self._memory_by_tenant.pop(oldest, None)
                    if evicted is not None:
                        try:
                            evicted.close()
                        except Exception as exc:
                            logger.debug("tenant memory close on evict skipped: %s", exc)
                mem = ButlerMemory(self._settings.butler_home, tenant_id=tid)
                self._memory_by_tenant[tid] = mem
        return mem

    def _rebuild_skill_router(self) -> None:
        from butler.tenant import resolve_tenant_for_project

        tid = resolve_tenant_for_project(
            self.project_manager.get_current(),
            self._settings,
        )
        mgr = combined_skill_manager(
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
            self.memory_offline = False
            self._memory_init_error = ""
            try:
                from butler.ops.degradation_registry import clear_degradation

                clear_degradation("memory")
            except Exception:
                pass
        except Exception as exc:
            logger.error(
                "Butler memory provider unavailable: %s",
                exc,
                exc_info=exc,
            )
            self.memory_provider = None
            self.memory_offline = True
            self._memory_init_error = f"{type(exc).__name__}: {exc}"
            try:
                from butler.ops.degradation_registry import register_degradation

                register_degradation(
                    "memory",
                    "初始化失败",
                    detail=self._memory_init_error[:200],
                )
            except Exception:
                pass

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

        role = normalize_butler_role(role)
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
        template = template_path()
        body = read_template_cached(template)
        if not body:
            if not template.exists():
                logger.warning("Butler system template missing at %s", template)

        current = self.project_manager.current_project or "(未选择)"
        project_list = format_project_list(self._settings)

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
            skills_block = format_skill_summaries(self._skill_manager.list_skills())

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
        except Exception as exc:
            logger.debug("system_reminder import skipped: %s", exc)
            return ""
        ph = self._system_prompt_placeholders(for_role=for_role)
        chunks = [
            "## 记忆与上下文\n" + (ph.get("memory_context") or "(无)"),
            "## 可用技能概要\n" + ph.get("skill_summaries", ""),
            "## 项目工作流\n" + ph.get("workflows_block", ""),
        ]
        if self.memory_offline:
            chunks.append(
                "## 记忆子系统离线 (memory offline)\n"
                "本次会话无法 recall 历史上下文,所有"
                " recall 类工具将返回空结果。"
                "请主动告知用户\"本次对话无历史记忆\","
                "避免产生已记住对方偏好的错觉。"
            )
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
        offline_appendix = ""
        if self.memory_offline:
            offline_appendix = (
                "\n\n## 记忆子系统离线 (memory offline)\n"
                "本次会话无法 recall 历史上下文,所有"
                " recall 类工具将返回空结果。"
                "请主动告知用户\"本次对话无历史记忆\","
                "避免产生已记住对方偏好的错觉。"
            )
        appendix = (
            "\n\n## Butler 模型\n"
            f"{ph['model_block']}\n\n"
            "## 可用技能概要\n"
            f"{ph['skill_summaries']}\n\n"
            "## 项目工作流\n"
            f"{ph['workflows_block']}"
        ) + offline_appendix
        return rendered.rstrip() + appendix

    def build_system_prompt(self) -> str:
        try:
            from butler.core.harness_flags import static_system_reminder_enabled

            if static_system_reminder_enabled():
                return self.build_static_system_prompt()
        except Exception as exc:
            logger.debug("Static system prompt check skipped: %s", exc)
        return self._assemble_default_system_prompt(for_role="default")

    def build_lead_system_prompt(self, *, session_key: str = "") -> str:
        """System prompt for project Lead gateway loop (phase 2)."""
        from butler.agent_profiles import get_profile

        path = lead_template_path()
        body = read_template_cached(path)
        if not body:
            if not path.exists():
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

            mc = self._model_credentials("butler")
            prov = mc.get("provider") or ""
            extra = get_model_aware_prompt_extra(str(prov))
            if extra:
                rendered += "\n\n" + extra
        return rendered.rstrip()

    def get_agent_kwargs(self) -> dict[str, Any]:
        return loop_factory.get_agent_kwargs(self)

    def create_llm_client(self, role: str = "butler") -> LLMClient:
        return loop_factory.create_llm_client(self, role)

    def create_agent_loop(
        self,
        role: str = "butler",
        *,
        tools: list[dict] | None = None,
        tool_dispatcher: Any = None,
        callbacks: Any = None,
        session_key: str = "",
    ) -> AgentLoop:
        return loop_factory.create_agent_loop(
            self,
            role,
            tools=tools,
            tool_dispatcher=tool_dispatcher,
            callbacks=callbacks,
            session_key=session_key,
        )

    def create_project_agent_loop(
        self,
        role: str = "dev",
        *,
        tools: list[dict] | None = None,
        tool_dispatcher: Any = None,
        callbacks: Any = None,
        session_key: str = "",
    ) -> AgentLoop:
        return loop_factory.create_project_agent_loop(
            self,
            role,
            tools=tools,
            tool_dispatcher=tool_dispatcher,
            callbacks=callbacks,
            session_key=session_key,
        )

    def get_project_agent_kwargs(self, role: str) -> dict[str, Any]:
        return loop_factory.get_project_agent_kwargs(self, role)

    def on_project_switch(self, old_project: str, new_project: str) -> None:
        logger.debug(
            "Butler project switched: %r -> %r",
            old_project,
            new_project,
        )
        self._reload_project_memory()
        self._rebuild_skill_router()
        self._refresh_memory_provider_for_project_switch()

    def _build_skill_injection_sections(
        self,
        matched: list[dict[str, Any]],
        *,
        header_note: str,
    ) -> list[str]:
        sections: list[str] = [
            "## 相关知识（Butler Skill）",
            "",
            header_note,
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
        return sections

    def inject_skill_context(
        self,
        task_description: str,
        top_k: int = 3,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> str:
        """Augment user text with skill bodies (experience-first policy via injection_policy)."""
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

        from butler.skills.injection_policy import resolve_skill_injection

        decision = resolve_skill_injection(
            self, task_description, diagnostics=diagnostics
        )
        if diagnostics is not None:
            diagnostics["skill_injection_reason"] = decision.reason

        router_note = (
            "> 以下内容来自与本任务相关的 Butler 技能（未验证参考），仅作上下文参考。"
        )
        ref_note = (
            "> 以下 Skill 由经验层 `skill:<名>` 指针点名加载（未验证参考）。"
        )

        if decision.skip:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_matches"] = []
            return task_description

        matched: list[dict[str, Any]] = []
        if decision.skill_names:
            manager = self._skill_manager
            if manager is None:
                if diagnostics is not None:
                    diagnostics["skill_context_injected"] = False
                    diagnostics["skill_matches"] = []
                return task_description
            loaded = manager.get_skills(list(decision.skill_names))
            for name in decision.skill_names:
                sk = loaded.get(name)
                if sk:
                    matched.append({**sk, "match_score": None})
            header_note = ref_note
        else:
            matched = self._skill_router.match(task_description, top_k=top_k)
            header_note = router_note

        if not matched:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_matches"] = []
            return task_description
        if diagnostics is not None:
            diagnostics["skill_matches"] = [
                str(sk.get("name")) for sk in matched if sk.get("name")
            ]

        sections = self._build_skill_injection_sections(
            matched, header_note=header_note
        )
        if len(sections) == 3:
            if diagnostics is not None:
                diagnostics["skill_context_injected"] = False
                diagnostics["skill_empty_matches"] = [
                    str(sk.get("name")) for sk in matched if sk.get("name")
                ]
            return task_description

        sections.append("")
        sections.append(task_description.strip())
        if diagnostics is not None:
            diagnostics["skill_context_injected"] = True
        return "\n".join(sections).strip()


__all__ = ["ButlerOrchestrator"]
