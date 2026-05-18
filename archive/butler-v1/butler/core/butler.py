"""Butler - the core AI agent that orchestrates everything.

v2: Project-scoped sessions, project memory, layered model config
v3: Structured report caching, channel-aware response guidelines, /detail support
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Callable

from butler.config.settings import settings
from butler.core.project_manager import project_manager
from butler.providers.base import CompletionResult, Message, ToolCall
from butler.providers.registry import get_provider_for_model
from butler.storage.butler_memory import ButlerMemory
from butler.storage.project_memory import ProjectMemory
from butler.storage.session_store import SessionStore
from butler.tools.registry import tool_registry

logger = logging.getLogger(__name__)

_MAX_TOOL_ITERATIONS = 20


class Butler:
    """The AI Butler - manages projects via tool calling with project-scoped context."""

    def __init__(
        self,
        user_id: str = "owner",
        channel: str = "cli",
    ):
        self.user_id = user_id
        self.channel = channel

        self.session_store = SessionStore(settings.db_path)
        self.global_memory = ButlerMemory.default()
        self._project_memory: ProjectMemory | None = None

        current_proj = project_manager.current_project
        self.session_id = self.session_store.get_or_create_session(user_id, channel, current_proj)
        self._history: list[Message] = []
        self._system_prompt: str = ""

        project_manager.on_switch(self._on_project_switch)
        self._ensure_tools_loaded()
        self._load_project_memory()
        self._build_system_prompt()

    @property
    def last_report(self):
        from butler.core import _last_report_cache
        return _last_report_cache.get()

    def get_last_report(self):
        """Return the cached AgentResult from the most recent agent delegation."""
        result = self.last_report
        if result is None:
            return None
        return result

    def _ensure_tools_loaded(self) -> None:
        import butler.tools.project_tools  # noqa: F401
        import butler.tools.file_tools  # noqa: F401
        import butler.tools.shell_tools  # noqa: F401
        import butler.tools.code_tools  # noqa: F401
        import butler.tools.patch_tool  # noqa: F401
        import butler.tools.git_tools  # noqa: F401
        import butler.tools.executor_tools  # noqa: F401
        import butler.tools.memory_tools  # noqa: F401
        import butler.tools.skill_tools  # noqa: F401

    def _load_project_memory(self) -> None:
        proj = project_manager.get_current()
        if proj:
            self._project_memory = ProjectMemory.for_project(proj)
        else:
            self._project_memory = None

    def _on_project_switch(self, old_project: str, new_project: str) -> None:
        self.session_id = self.session_store.get_or_create_session(
            self.user_id, self.channel, new_project,
        )
        self._history.clear()
        self._load_project_memory()
        self._build_system_prompt()
        logger.info(f"Switched session to project '{new_project}' (session={self.session_id[:8]})")

    def _build_system_prompt(self) -> str:
        prompt_path = Path(__file__).parent.parent / "config" / "prompts" / "butler.md"
        template = prompt_path.read_text(encoding="utf-8")

        projects = project_manager.list_projects()
        project_list = ", ".join(p.name for p in projects) if projects else "(暂无项目)"
        current = project_manager.current_project or "(未选择)"
        global_ctx = self.global_memory.get_system_context(current_project=current)

        project_memory_ctx = ""
        model_info = ""
        if self._project_memory:
            project_memory_ctx = self._project_memory.get_full_context(max_lines=40)

        proj = project_manager.get_current()
        if proj:
            butler_mc = settings.get_model_config("butler")
            dev_mc = proj.resolve_model("dev_agent")
            content_mc = proj.resolve_model("content_agent")
            model_info = (
                f"\n当前模型配置:\n"
                f"  管家: {butler_mc.provider}:{butler_mc.model}\n"
                f"  DevAgent: {dev_mc.provider}:{dev_mc.model}\n"
                f"  ContentAgent: {content_mc.provider}:{content_mc.model}"
            )

        memory_block = global_ctx or "(暂无管家层记忆)"
        if project_memory_ctx:
            memory_block += f"\n\n--- 当前项目记忆 ---\n{project_memory_ctx}"
        if model_info:
            memory_block += model_info

        self._system_prompt = template.format(
            butler_name=settings.butler_name,
            owner_name=settings.owner_name,
            current_project=current,
            project_list=project_list,
            memory_context=memory_block,
        )
        return self._system_prompt

    def _get_butler_provider(self):
        butler_model = settings.get_model_config("butler")
        return get_provider_for_model(butler_model), butler_model

    def set_progress_handler(self, handler: Callable[[int, str, str], None] | None) -> None:
        """Set a callback to receive real-time progress during agent execution."""
        from butler.core import _progress_handler
        _progress_handler.set(handler)

    async def chat(
        self,
        user_input: str,
        stream_callback: Callable[[str], None] | None = None,
    ) -> str:
        self._build_system_prompt()

        user_msg = Message.user(user_input)
        self._history.append(user_msg)
        self.session_store.append_message(self.session_id, user_msg)

        messages = [Message.system(self._system_prompt)] + self._history

        tool_defs = tool_registry.get_definitions()
        provider, butler_model = self._get_butler_provider()
        full_response = ""

        for _ in range(_MAX_TOOL_ITERATIONS):
            if stream_callback:
                result = await self._stream_completion(
                    provider, butler_model, messages, tool_defs, stream_callback,
                )
            else:
                result = await provider.complete(
                    messages, tools=tool_defs,
                    model=butler_model.model or None,
                    temperature=butler_model.temperature,
                    max_tokens=butler_model.max_tokens,
                )

            assistant_msg = result.message
            messages.append(assistant_msg)
            self._history.append(assistant_msg)
            self.session_store.append_message(self.session_id, assistant_msg)

            if not assistant_msg.tool_calls:
                full_response = assistant_msg.content
                break

            tool_results = await self._execute_tool_calls(assistant_msg.tool_calls)
            for tr_msg in tool_results:
                messages.append(tr_msg)
                self._history.append(tr_msg)
                self.session_store.append_message(self.session_id, tr_msg)
        else:
            full_response = assistant_msg.content or "(达到工具调用上限，请缩小任务范围)"

        return full_response

    async def _stream_completion(self, provider, model_config, messages, tools, callback):
        collected_text = ""
        collected_tool_calls: list[ToolCall] = []

        async for delta in provider.stream(
            messages, tools=tools,
            model=model_config.model or None,
            temperature=model_config.temperature,
            max_tokens=model_config.max_tokens,
        ):
            if delta.text:
                collected_text += delta.text
                callback(delta.text)
            if delta.tool_call:
                collected_tool_calls.append(delta.tool_call)

        msg = Message.assistant(collected_text, tool_calls=collected_tool_calls or None)
        return CompletionResult(message=msg)

    async def _execute_tool_calls(self, tool_calls: list[ToolCall]) -> list[Message]:
        results: list[Message] = []
        for tc in tool_calls:
            logger.info(f"Executing tool: {tc.name}({list(tc.arguments.keys())})")
            result_str = await tool_registry.dispatch(tc.name, tc.arguments)
            results.append(Message.tool(tc.id, result_str))
        return results

    def new_session(self) -> str:
        self._try_extract_memory()
        current_proj = project_manager.current_project
        self.session_id = self.session_store.create_session(self.user_id, self.channel, current_proj)
        self._history.clear()
        return self.session_id

    def _try_extract_memory(self) -> None:
        if not self._history:
            return
        try:
            import asyncio
            loop = asyncio.get_event_loop()
            coro = self._run_post_session()
            if loop.is_running():
                asyncio.create_task(coro)
            else:
                loop.run_until_complete(coro)
        except Exception as e:
            logger.debug(f"Post-session processing skipped: {e}")

    async def _run_post_session(self) -> None:
        """Run PostSessionProcessor for dual-channel extraction (memory + skill)."""
        from butler.agent.post_session import PostSessionProcessor
        from butler.tools.skill_tools import _get_loader

        processor = PostSessionProcessor()
        project_name = project_manager.current_project or ""

        skill_loader = None
        try:
            skill_loader = _get_loader()
        except Exception:
            pass

        result = await processor.process(
            messages=self._history,
            butler_memory=self.global_memory,
            project_memory=self._project_memory,
            skill_loader=skill_loader,
            project_name=project_name,
        )
        if result.get("memory_updates") or result.get("skills_extracted"):
            logger.info(
                "Post-session: %d memory updates, %d skills extracted",
                result.get("memory_updates", 0),
                result.get("skills_extracted", 0),
            )

    def load_session(self, session_id: str) -> None:
        self.session_id = session_id
        self._history = self.session_store.get_history(session_id)

    async def close(self) -> None:
        self._try_extract_memory()
        self.set_progress_handler(None)
        provider, _ = self._get_butler_provider()
        await provider.close()
        self.session_store.close()
