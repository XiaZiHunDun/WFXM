"""Butler Agent Loop — the core LLM conversation engine."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, cast
from contextlib import AbstractContextManager
from collections.abc import Iterator

from butler.core.context_pipeline import ContextPipeline
from butler.core.delegate_context import set_parent_callbacks
from butler.core.llm_retry import call_llm_with_retry
from butler.core.loop_response import (
    needs_truncation_continue,
    truncation_continue_message,
)
from butler.core.loop_types import (
    LoopCallbacks,
    LoopConfig,
    LoopResult,
    LoopStatus,
    LoopTransitionReason,
)
from butler.core.message_sanitize import sanitize_surrogates
from butler.core.tool_batch import (
    ToolBatchStats,
    dispatch_tool_with_envelope,
    process_tool_calls,
)
from butler.tool_guardrails import ToolCallGuardrailController
from butler.core.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.core.steer import clear_steer, mark_run_active, mark_run_inactive
from butler.transport.base import LLMClientProtocol
from butler.transport.fallback import FallbackEntry, create_client_from_entry
from butler.transport.llm_client import LLMClient
from butler.transport.types import NormalizedResponse

from butler.core.agent_loop.phases import (
    TurnBodyState,
    _mark_interrupted_status,
    _phase_call_llm,
    _phase_dispatch_tools,
    _phase_finalize,
    _phase_init,
    _phase_resolve_user_text,
    _phase_enrich_user_text,
)

from butler.core.agent_loop_ops import (
    apply_reflexion_safe,
    doom_loop_block_on_ask,
    emit_skipped_plugin_metric,
    filter_fallback_chain_safe,
    maybe_compact_turn_safe,
    record_provider_failure_safe,
    refresh_model_binding_safe,
    run_after_tools_plugins_safe,
    run_stop_hooks_safe,
)
from butler.core.best_effort import record_best_effort_skip
from butler.core.conversation_state import ConversationState, build_conversation_reminder
from butler.core.delegate_context import (
    set_parent_messages,
    set_parent_system_prompt,
)
from butler.core.hook_context_adapter import (
    adapt_hook_context_lines,
    apply_hook_context_to_diagnostics,
    to_hook_context_view,
)
from butler.core.loop_callbacks_merge import merge_loop_callbacks
from butler.core.loop_plugins import default_plugin_registry
from butler.core.session_transcript import transcript_batch
from butler.core.streaming_tools import streaming_tools_enabled
from butler.core.tool_call_limits import reset_tool_call_limiter_for_turn
from butler.execution_context import (
    get_current_orchestrator,
    get_current_session_key,
    use_execution_context,
)
from butler.mcp.turn_scrape_dedup import turn_scrape_dedup_scope
from butler.memory.experience.retriever import ExperienceRetriever
from butler.memory.experience.writer import ExperienceWriter
from butler.memory.semantic_index import SemanticMemoryIndex, get_embedder
from butler.tool_guardrails import synthetic_result
from butler.tools.conversation_state_tools import load_conversation_state, persist_conversation_state
from butler.tools.network_search_policy import turn_network_search_scope
from butler.tools.tool_service import get_tool_service
from butler.transport.provider_health import is_circuit_open
from butler.core.turn_summarizer import summarize_chapter, summarize_turn, _extract_file_changes

logger = logging.getLogger(__name__)

_MAX_SKIPPED_PLUGIN_ENTRIES = 50
_MAX_SKIPPED_PLUGIN_ERROR_LEN = 200


class AgentLoop:
    """Self-contained LLM conversation loop with tool calling."""

    def __init__(
        self,
        client: LLMClientProtocol,
        *,
        system_prompt: str = "",
        tools: Optional[list[dict[str, Any]]] = None,
        tool_dispatcher: Optional[Callable[[str, dict[str, Any]], str]] = None,
        config: Optional[LoopConfig] = None,
        callbacks: Optional[LoopCallbacks] = None,
    ):
        self.client: LLMClientProtocol = client
        self.system_prompt = system_prompt
        self.tools = tools or []
        self.tool_dispatcher = tool_dispatcher
        self.config = config or LoopConfig()
        self.callbacks = callbacks or LoopCallbacks()

        self._messages: list[dict[str, Any]] = []
        self._turn_tools: list[dict[str, Any]] | None = None
        self._interrupted = False
        self._total_tokens = 0
        self._tool_calls_count = 0
        self._guardrails = ToolCallGuardrailController() if self.config.enable_guardrails else None
        self._context = ContextPipeline(self.config)
        self._context.attach_loop(self)
        self._turn_ephemeral_system: str | None = None
        self._thread_id: int | None = None
        self.diagnostics: dict[str, Any] = {}
        _chain = list(self.config.fallback_entries or [])
        _chain = filter_fallback_chain_safe(_chain)
        self._fallback_chain: list[FallbackEntry] = _chain
        self._fallback_index = 0
        self._primary_client: LLMClient | None = None
        self._empty_retries = 0
        self._truncation_retries = 0
        self._tool_prefetch: dict[str, str] = {}
        self._orchestrator: Any | None = None
        self._session_key: str = ""
        self._loop_role: str = ""
        self._plugins = default_plugin_registry(self.config)
        self._conversation_state: Any = None
        self._turn_count: int = 0

    def bind_execution(
        self,
        orchestrator: Any | None = None,
        *,
        session_key: str = "",
        loop_role: str = "",
    ) -> None:
        """Bind orchestrator/session/role for tool dispatch when contextvars are missing."""
        if orchestrator is not None:
            self._orchestrator = orchestrator
        self._session_key = str(session_key or self._session_key or "")
        if loop_role:
            self._loop_role = str(loop_role).strip().lower()

    def _tool_execution_context(self) -> AbstractContextManager[None]:
        from contextlib import contextmanager

        @contextmanager
        def _ctx() -> Iterator[None]:
            orch = get_current_orchestrator() or self._orchestrator
            sk = str(get_current_session_key() or self._session_key or "")
            role = str(self._loop_role or "").strip().lower()
            if orch is None and not sk:
                yield
                return
            with use_execution_context(orch, session_key=sk, loop_role=role):
                yield

        return _ctx()

    @property
    def _compression_summary(self) -> str:
        return str(self._context.compression_summary)

    @_compression_summary.setter
    def _compression_summary(self, value: str) -> None:
        self._context.compression_summary = value

    def interrupt(self) -> None:
        self._interrupted = True
        if self._thread_id is not None:
            set_interrupt(True, self._thread_id)

    def clear_interrupt(self) -> None:
        self._interrupted = False
        if self._thread_id is not None:
            clear_interrupt(self._thread_id)

    def _record_skipped_plugin(self, plugin_name: str, exc: BaseException) -> None:
        """Record a skipped plugin/middleware to ``diagnostics['skipped']``."""
        label = f"agent_loop.{plugin_name}"
        logger.error("%s skipped: %s", plugin_name, exc, exc_info=exc)
        record_best_effort_skip(label, exc)
        emit_skipped_plugin_metric(label)
        bucket = self.diagnostics.setdefault("skipped", [])
        bucket.append({
            "plugin": plugin_name,
            "error": str(exc)[:_MAX_SKIPPED_PLUGIN_ERROR_LEN],
            "type": type(exc).__name__,
        })
        if len(bucket) > _MAX_SKIPPED_PLUGIN_ENTRIES:
            del bucket[: len(bucket) - _MAX_SKIPPED_PLUGIN_ENTRIES]

    def run(
        self,
        user_message: str,
        *,
        run_callbacks: Optional[LoopCallbacks] = None,
        ephemeral_system: str | None = None,
    ) -> LoopResult:
        start_time = time.time()
        saved_callbacks = self.callbacks
        if run_callbacks is not None:
            self.callbacks = merge_loop_callbacks(saved_callbacks, run_callbacks)
        pre_run_diagnostics = {
            k: v for k, v in self.diagnostics.items()
            if str(k).startswith("hygiene_")
        }
        self.diagnostics = dict(pre_run_diagnostics)
        self._turn_count += 1
        self._turn_ephemeral_system = self._build_turn_ephemeral_system(ephemeral_system)
        if self._turn_ephemeral_system:
            self.diagnostics["ephemeral_system_injected"] = True
        self._interrupted = False
        self._thread_id = threading.get_ident() if hasattr(threading, "get_ident") else None
        clear_interrupt(self._thread_id)
        _steer_session = get_current_session_key() or "default"
        mark_run_active(_steer_session)
        try:
            with transcript_batch(_steer_session):
                with turn_network_search_scope(user_message):
                    with turn_scrape_dedup_scope():
                        result = self._run_turn_body(
                            user_message,
                            run_callbacks=run_callbacks,
                            saved_callbacks=saved_callbacks,
                            pre_run_diagnostics=pre_run_diagnostics,
                            start_time=start_time,
                            steer_session=_steer_session,
                        )
                        self._update_conversation_state(user_message, result)
                        return result
        finally:
            mark_run_inactive(_steer_session)

    def _init_turn_state(self, steer_session: str) -> None:
        """Reset per-turn mutable state before the iteration loop."""
        clear_steer(steer_session)
        self._primary_client = self.client
        self._fallback_index = 0
        self._empty_retries = 0
        self._truncation_retries = 0
        set_parent_callbacks(self.callbacks)
        set_parent_system_prompt(self.system_prompt)
        set_parent_messages(self._messages)
        self._tool_prefetch.clear()
        if self._guardrails:
            self._guardrails.reset_for_turn()
        reset_tool_call_limiter_for_turn()
        self._init_conversation_state()

    def _init_conversation_state(self) -> None:
        """Initialize conversation state — lazy-load from disk on first turn."""
        if self._conversation_state is None:
            restored = None
            if self._should_restore_state():
                restored = load_conversation_state()

            if restored is not None:
                self._conversation_state = restored
                self._turn_count = len(restored.turn_summaries)
                self.diagnostics["conversation_state_restored"] = True
            else:
                self._conversation_state = ConversationState()

    def _should_restore_state(self) -> bool:
        """Check if cross-session state restoration is enabled."""
        import os

        return os.getenv("BUTLER_CONVERSATION_STATE_PERSIST", "1") == "1"

    def _persist_conversation_state(self) -> None:
        """Persist conversation state to disk for cross-session recovery."""
        if self._conversation_state is None:
            return
        if not self._should_restore_state():
            return
        persist_conversation_state(self._conversation_state)

    def _build_turn_ephemeral_system(self, ephemeral_system: str | None) -> str | None:
        """Build ephemeral system message with conversation state and experience injected."""
        from butler.core.best_effort import safe_best_effort

        parts: list[str] = []
        if ephemeral_system:
            parts.append(str(ephemeral_system))

        if self._conversation_state:
            reminder = build_conversation_reminder(self._conversation_state, token_budget=2000)
            if reminder:
                parts.append(reminder)

        def _inject_experience() -> str | None:
            try:
                retriever = ExperienceRetriever()

                recent_intents = []
                if self._conversation_state:
                    for turn in self._conversation_state.turn_summaries[-5:]:
                        if turn.user_intent:
                            recent_intents.append(turn.user_intent)
                if not recent_intents:
                    return None

                query = " ".join(recent_intents)[:500]
                experiences = retriever.retrieve("default", query, top_k=3)

                if not experiences:
                    return None

                experience_lines = []
                for exp in experiences:
                    content = exp.node.content if hasattr(exp.node, "content") else str(exp.node)
                    source = exp.source if hasattr(exp, "source") else "experience"
                    score = exp.score if hasattr(exp, "score") else 0.0
                    if score > 0.3:
                        experience_lines.append(
                            f"[经验 {source} 得分={score:.2f}]: {content[:200]}"
                        )

                if experience_lines:
                    self.diagnostics["experience_injected"] = len(experience_lines)
                    return "\n\n".join(
                        ["## 相关历史经验"] + experience_lines
                    )
                return None
            except Exception as e:
                logger.debug("Experience injection failed: %s", e)
                return None

        experience_section = safe_best_effort(
            _inject_experience,
            label="agent_loop.experience_injection",
            default=None,
        )
        if experience_section:
            parts.append(experience_section)

        if not parts:
            return None
        return "\n\n".join(parts)

    def _update_conversation_state(self, user_message: str, result: Any) -> None:
        """Update conversation state after each turn completes."""
        from butler.core.best_effort import safe_best_effort

        if self._conversation_state is None:
            return

        diag = result.diagnostics if result.diagnostics else {}
        tool_calls_detail = diag.get("tool_calls_detail", [])

        files_touched: list[str] = []
        for tc in tool_calls_detail:
            name = str(tc.get("name", "") or "")
            args = tc.get("args", {}) or {}
            if name in ("read_file", "write_file", "patch", "delete_file"):
                file_path = str(args.get("file_path") or args.get("path") or "")
                if file_path:
                    files_touched.append(file_path)

        file_changes = _extract_file_changes(tool_calls_detail)
        for fc in file_changes:
            if fc["path"]:
                self._conversation_state.add_file_change(
                    path=fc["path"],
                    operation=fc["operation"],
                    description=fc["description"],
                    turn_number=self._turn_count,
                )

        self._auto_detect_branch_and_build_status(tool_calls_detail, diag)

        summary = summarize_turn(
            user_message=user_message,
            assistant_response=result.final_response or "",
            tool_calls_detail=tool_calls_detail,
        )

        self._conversation_state.add_turn_summary(
            turn_number=self._turn_count,
            user_intent=summary["user_intent"],
            assistant_action=summary["assistant_action"],
            result_summary=summary["result_summary"],
            files_touched=files_touched,
        )

        if self._turn_count == 1:
            self._conversation_state.update_conversation_goal(user_message[:500])
            self._conversation_state.update_task_summary(user_message[:500])

        self._try_generate_chapter_summary()
        self._try_embed_chapter_to_semantic_memory()

        def _write_experience() -> None:
            try:
                if not tool_calls_detail:
                    return

                writer = ExperienceWriter()
                metadata = {
                    "turn_number": self._turn_count,
                    "files_touched": files_touched[:10],
                    "tool_calls": len(tool_calls_detail),
                    "session_id": getattr(self, "_session_id", ""),
                }

                for tc in tool_calls_detail[:5]:
                    tc_name = str(tc.get("name", ""))
                    tc_args = tc.get("args", {}) or {}
                    tc_result = str(tc.get("result", ""))[:500]

                    if tc.get("success", True):
                        query_part = f"{user_message[:100]} -> {tc_name}"
                        result_part = tc_result or summary.get("result_summary", "")[:200]

                        writer.write(
                            query=query_part,
                            result=result_part,
                            metadata={**metadata, "tool_name": tc_name},
                        )

                self.diagnostics["experience_written"] = len(tool_calls_detail)
            except Exception as e:
                logger.debug("Experience write failed: %s", e)

        safe_best_effort(
            _write_experience,
            label="agent_loop.experience_write",
        )

        self.diagnostics["conversation_state"] = self._conversation_state
        self._persist_conversation_state()

    def _auto_detect_branch_and_build_status(self, tool_calls_detail: list[dict[str, Any]], diag: dict[str, Any]) -> None:
        """Auto-detect git branch and build status from terminal tool outputs."""
        import re

        for tc in tool_calls_detail:
            name = str(tc.get("name", "") or "")
            args = tc.get("args", {}) or {}
            cmd = str(args.get("command", "") or "")

            if name == "terminal":
                if "git branch" in cmd or "git status" in cmd:
                    output = str(args.get("output", "") or "")
                    match = re.search(r"\* (.*)", output)
                    if match:
                        self._conversation_state.current_branch = match.group(1).strip()[:50]

                if ("pytest" in cmd or "python -m pytest" in cmd or
                    "build" in cmd or "make" in cmd or "setup.py" in cmd):
                    output = str(args.get("output", "") or "")
                    if "FAILED" in output or "Error" in output or "error" in output:
                        self._conversation_state.last_build_status = "FAILED"
                    elif "passed" in output.lower() or "success" in output.lower():
                        self._conversation_state.last_build_status = "PASSED"

        if "tool_results" in diag:
            for tr in diag["tool_results"]:
                if tr.get("tool_name") == "terminal":
                    output = str(tr.get("result", "") or "")
                    if self._conversation_state.current_branch == "":
                        match = re.search(r"\* (.*)", output)
                        if match:
                            self._conversation_state.current_branch = match.group(1).strip()[:50]
                    if self._conversation_state.last_build_status == "":
                        if "FAILED" in output or "Error" in output or "error" in output:
                            self._conversation_state.last_build_status = "FAILED"
                        elif "passed" in output.lower() or "success" in output.lower():
                            self._conversation_state.last_build_status = "PASSED"

    def _try_generate_chapter_summary(self) -> None:
        """Generate a chapter summary every 10 turns."""
        if self._turn_count % 10 != 0:
            return
        if self._conversation_state is None:
            return

        chapter_number = self._turn_count // 10
        start_turn = (chapter_number - 1) * 10 + 1
        end_turn = self._turn_count

        summaries = []
        for i in range(start_turn, end_turn + 1):
            summary = self._conversation_state.get_turn_summary(i)
            if summary:
                summaries.append(f"Turn {i}: {summary.user_intent or ''}")

        if summaries:
            chapter_text = "\n".join(summaries)
            chapter_summary = summarize_chapter(chapter_text)
            if chapter_summary:
                self._conversation_state.add_chapter_summary(
                    chapter_number=chapter_number,
                    summary=chapter_summary,
                )
                self.diagnostics["chapter_summary_generated"] = chapter_number

    def _try_embed_chapter_to_semantic_memory(self) -> None:
        """Embed chapter summary to semantic memory for retrieval."""
        if self._turn_count % 10 != 0:
            return
        if self._conversation_state is None:
            return

        chapter_number = self._turn_count // 10
        chapter_summary = self._conversation_state.get_chapter_summary(chapter_number)
        if not chapter_summary:
            return

        try:
            index = SemanticMemoryIndex()
            embedder = get_embedder()
            if embedder is None:
                return

            embedding = embedder.embed(chapter_summary)
            index.add(
                text=chapter_summary,
                embedding=embedding,
                metadata={"chapter": chapter_number, "turn_count": self._turn_count},
            )
            self.diagnostics["chapter_embedded"] = chapter_number
        except Exception as e:
            logger.debug("Chapter embedding failed: %s", e)

    def _prepare_user_message(
        self,
        user_message: str,
    ) -> tuple[str, list[dict[str, Any]]]:
        """Prepare user message with network search if enabled."""
        from butler.tools.network_search_policy import (
            turn_network_search_scope,
            should_run_network_search,
            run_network_search,
        )

        if should_run_network_search(user_message):
            search_results = run_network_search(user_message)
            if search_results:
                self.diagnostics["network_search_results"] = len(search_results)
                search_context = "\n\n".join([
                    f"[搜索结果 {i+1}]: {r['title']}\n{r['summary']}"
                    for i, r in enumerate(search_results[:5])
                ])
                enriched_message = f"{user_message}\n\n## 网络搜索结果\n{search_context}"
                return enriched_message, []

        return user_message, []

    def _run_turn_body(
        self,
        user_message: str,
        *,
        run_callbacks: Optional[LoopCallbacks] = None,
        saved_callbacks: LoopCallbacks,
        pre_run_diagnostics: dict[str, Any],
        start_time: float,
        steer_session: str,
    ) -> LoopResult:
        """Main turn body — orchestrates phases and iteration loop."""
        state = TurnBodyState()
        _phase_init(self, user_message, steer_session, state)

        while True:
            state.iteration += 1

            if self._interrupt_check():
                _mark_interrupted_status(state)
                break

            _phase_resolve_user_text(self, state)
            _phase_enrich_user_text(self, state)
            maybe_compact_turn_safe(self, state)

            _phase_call_llm(self, state)
            if state.response is None:
                break

            _phase_dispatch_tools(self, state.response, state, start_time, state.steer_session)
            if state.status != LoopStatus.RUNNING:
                break

            apply_reflexion_safe(self)

            if self._maybe_stop_hook_continue(
                steer_session=steer_session,
                iteration=state.iteration,
                start_time=start_time,
                final_text=state.final_text or "",
            ):
                break

        _phase_finalize(self, state, run_callbacks=run_callbacks, steer_session=steer_session, start_time=start_time)

        return state.result

    def _maybe_stop_hook_continue(
        self,
        *,
        steer_session: str,
        iteration: int,
        start_time: float,
        final_text: str,
    ) -> bool:
        """Check stop hooks and budget for continuation."""
        result = run_stop_hooks_safe(
            self,
            steer_session=steer_session,
            iteration=iteration,
            start_time=start_time,
            final_text=final_text,
        )
        if result is not None and getattr(result, "blocked", False):
            self._result = result
            return True
        return False

    def _restore_primary_client(self) -> None:
        """Restore primary client after fallback chain exhaustion."""
        if self._primary_client is not None:
            self.client = self._primary_client
            self._primary_client = None

    def _estimate_tokens(self, messages: list[dict[str, Any]]) -> int:
        """Estimate token count for messages."""
        return sum(len(str(m.get("content", ""))) // 4 for m in messages)

    def hygiene_compress_if_needed(
        self,
        messages: list[dict[str, Any]],
        *,
        user_message: str,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Compress context if needed based on hygiene thresholds."""
        compressed, result = self._context.hygiene_compress_if_needed(
            messages,
            self.diagnostics,
            user_message=user_message,
        )
        return compressed, result

    def _compress_context(
        self,
        messages: list[dict[str, Any]],
        *,
        threshold_ratio: float = 0.5,
        min_messages_to_compress: int = 12,
        diagnostics: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Compress context via the pipeline."""
        return cast(
            list[dict[str, Any]],
            self._context.compress_context(
                messages,
                threshold_ratio=threshold_ratio,
                min_messages_to_compress=min_messages_to_compress,
                diagnostics=diagnostics if diagnostics else self.diagnostics,
            ),
        )

    def _prepare_messages_for_api(self) -> list[dict[str, Any]]:
        """Prepare messages for LLM API call."""
        messages = []

        if self.system_prompt:
            messages.append({"role": "system", "content": self.system_prompt})

        if self._turn_ephemeral_system:
            messages.append({"role": "system", "content": self._turn_ephemeral_system})

        messages.extend(self._messages)

        return messages

    def _try_activate_fallback(self) -> bool:
        """Try to activate the next fallback client."""
        if self._fallback_index >= len(self._fallback_chain):
            return False

        entry = self._fallback_chain[self._fallback_index]
        self._fallback_index += 1

        try:
            fallback_client = create_client_from_entry(entry)
            self.client = fallback_client
            self.diagnostics["fallback_activated"] = entry.model
            logger.info("Activated fallback client: %s", entry.model)
            return True
        except Exception as e:
            logger.error("Failed to activate fallback %s: %s", entry.model, e)
            record_provider_failure_safe(entry.model, str(e))
            return self._try_activate_fallback()

    def _interrupt_check(self) -> bool:
        """Check if the loop has been interrupted."""
        if self._interrupted:
            return True
        if self._thread_id is not None and is_interrupted(self._thread_id):
            self._interrupted = True
            return True
        return False

    def _call_llm_with_retry(self) -> Optional[NormalizedResponse]:
        """Call LLM with retry logic."""
        messages = self._prepare_messages_for_api()

        if self._interrupt_check():
            return None

        from butler.core.context_compressor import compress_messages

        def _compress_messages(msg: list[dict[str, Any]]) -> list[dict[str, Any]]:
            compressed, _, _ = compress_messages(
                msg,
                max_tokens=self.config.max_context_tokens,
                diagnostics=self.diagnostics,
            )
            return cast(list[dict[str, Any]], compressed)

        response, interrupted = call_llm_with_retry(
            client=self.client,
            config=self.config,
            callbacks=self.callbacks,
            tools=self._turn_tools or self.tools or [],
            messages=messages,
            diagnostics=self.diagnostics,
            prepare_messages=self._prepare_messages_for_api,
            compress_messages=_compress_messages,
            interrupt_check=self._interrupt_check,
            try_activate_fallback=self._try_activate_fallback,
            empty_retries=[self._empty_retries],
        )
        if interrupted:
            return None

        # Emit LLMApiCallEvent for event sourcing
        self._emit_llm_api_call_event(response)

        return response

    def _emit_llm_api_call_event(self, response: NormalizedResponse) -> None:
        """Emit LLMApiCallEvent for event sourcing."""
        from butler.core.event_store_events import create_llm_api_call_event
        from butler.core.best_effort import safe_best_effort

        def _emit() -> None:
            event = create_llm_api_call_event(
                session_key=str(self._session_key or ""),
                provider=str(getattr(self.client, "provider", "") or ""),
                model=str(getattr(self.client, "model", "") or ""),
                prompt_tokens=getattr(response, "prompt_tokens", 0),
                completion_tokens=getattr(response, "completion_tokens", 0),
                duration_ms=getattr(response, "duration_ms", 0),
                is_streaming=False,
            )
            # Append to event store (append-only, no state replacement)
            from butler.core.event_store import append_event
            append_event(event)

        safe_best_effort(_emit, label="agent_loop.llm_api_call_event")

    def _process_tool_calls(self, response: NormalizedResponse) -> ToolBatchStats:
        """Process tool calls from LLM response."""
        if self._interrupt_check():
            return ToolBatchStats()

        with self._tool_execution_context():
            stats = process_tool_calls(
                response=response,
                messages=self._prepare_messages_for_api(),
                config=self.config,
                callbacks=self.callbacks,
                guardrails=self._guardrails,
                dispatch_tool=self._dispatch_tool,
                interrupt_check=self._interrupt_check,
                prefetched=self._tool_prefetch or None,
            )

        run_after_tools_plugins_safe(self, stats)
        self._tool_calls_count += stats.tools_started

        return stats

    def _dispatch_tool(self, name: str, args: dict[str, Any]) -> str:
        """Dispatch a single tool call."""
        with self._tool_execution_context():
            def _inner(n: str, a: dict[str, Any]) -> str:
                if self.tool_dispatcher:
                    return self.tool_dispatcher(n, a)
                service = get_tool_service()
                return cast(str, service.call_tool(n, a))

            return cast(str, dispatch_tool_with_envelope(_inner, name, args))

    @property
    def messages(self) -> list[dict[str, Any]]:
        return self._messages.copy()

    @messages.setter
    def messages(self, value: list[dict[str, Any]]) -> None:
        self._messages = list(value)

    def reset(self) -> None:
        """Reset the loop state."""
        self._messages = []
        self._turn_tools = None
        self._interrupted = False
        self._total_tokens = 0
        self._tool_calls_count = 0
        self._fallback_index = 0
        self._empty_retries = 0
        self._truncation_retries = 0
        self._tool_prefetch.clear()
        self.diagnostics = {}