"""Butler Orchestrator — bridges Butler product layer with the Agent Loop."""

from __future__ import annotations

import logging
import threading
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.core.agent_loop import AgentLoop
    from butler.transport.llm_client import LLMClient

from butler.config import get_butler_settings
from butler.memory import ButlerMemory, ProjectMemory
from butler.memory.facade import ButlerMemoryService  # test patch target
from butler.orchestrator import loop_factory, memory_bridge, prompt_assembler, skill_bridge
from butler.orchestrator.templates import normalize_butler_role
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
        memory_bridge.reload_project_memory(self)
        skill_bridge.rebuild_skill_router(self)
        memory_bridge.initialize_memory_provider(self)
        self.project_manager.on_switch(self._pm_switch)

    def _pm_switch(self, old_project: str, new_project: str) -> None:
        self.on_project_switch(old_project, new_project)

    @property
    def butler_memory(self) -> ButlerMemory:
        return memory_bridge.get_butler_memory(self)

    def _model_credentials(self, role: str) -> dict[str, Any]:
        from butler.model_resolve import model_config_to_credentials, resolve_effective_model

        role = normalize_butler_role(role)
        project = self.project_manager.get_current()
        em = resolve_effective_model(role, project=project, settings=self._settings)
        return model_config_to_credentials(em.config, settings=self._settings)

    def build_memory_context(self, *, for_role: str = "default") -> str:
        return memory_bridge.build_memory_context(self, for_role=for_role)

    def _system_prompt_placeholders(self, *, for_role: str = "default") -> dict[str, str]:
        return prompt_assembler.system_prompt_placeholders(self, for_role=for_role)

    def build_dynamic_system_reminder(self, *, for_role: str = "default") -> str:
        return prompt_assembler.build_dynamic_system_reminder(self, for_role=for_role)

    def build_static_system_prompt(self) -> str:
        return prompt_assembler.build_static_system_prompt(self)

    def resolve_system_prompt(
        self,
        *,
        role: str = "butler",
        session_key: str = "",
    ) -> tuple[str, str | None]:
        return prompt_assembler.resolve_system_prompt(
            self, role=role, session_key=session_key
        )

    def _assemble_default_system_prompt(self, *, for_role: str = "default") -> str:
        return prompt_assembler.assemble_default_system_prompt(self, for_role=for_role)

    def build_system_prompt(self) -> str:
        return prompt_assembler.build_system_prompt(self)

    def build_lead_system_prompt(self, *, session_key: str = "") -> str:
        return prompt_assembler.build_lead_system_prompt(self, session_key=session_key)

    def get_agent_kwargs(self) -> dict[str, Any]:
        return loop_factory.get_agent_kwargs(self)

    def create_llm_client(self, role: str = "butler") -> LLMClient:
        return loop_factory.create_llm_client(self, role)

    def create_agent_loop(
        self,
        role: str = "butler",
        *,
        tools: list[dict[str, Any]] | None = None,
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
        tools: list[dict[str, Any]] | None = None,
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
        memory_bridge.reload_project_memory(self)
        skill_bridge.rebuild_skill_router(self)
        memory_bridge.refresh_memory_provider_for_project_switch(self)

    def _reload_project_memory(self) -> None:
        memory_bridge.reload_project_memory(self)

    def _rebuild_skill_router(self) -> None:
        skill_bridge.rebuild_skill_router(self)

    def _initialize_memory_provider(self) -> None:
        memory_bridge.initialize_memory_provider(self)

    def _refresh_memory_provider_for_project_switch(self) -> None:
        memory_bridge.refresh_memory_provider_for_project_switch(self)

    def _build_skill_injection_sections(
        self,
        matched: list[dict[str, Any]],
        *,
        header_note: str,
    ) -> list[str]:
        return skill_bridge.build_skill_injection_sections(
            matched, header_note=header_note
        )

    def inject_skill_context(
        self,
        task_description: str,
        top_k: int = 3,
        *,
        diagnostics: dict[str, Any] | None = None,
    ) -> str:
        return skill_bridge.inject_skill_context(
            self,
            task_description,
            top_k=top_k,
            diagnostics=diagnostics,
        )


__all__ = ["ButlerOrchestrator", "ButlerMemoryService"]
