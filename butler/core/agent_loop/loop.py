"""Butler Agent Loop — the core LLM conversation engine.

Split into modules:
  - loop_conversation.py: conversation state management, experience injection, summaries
  - loop_helpers.py: LLM calls, tool dispatch, context compression utilities
  - phases/: turn execution phases
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Any, Callable, Optional, cast
from contextlib import AbstractContextManager
from collections.abc import Iterator

from butler.core.context_pipeline import ContextPipeline
from butler.core.loop_types import (
    LoopCallbacks,
    LoopConfig,
    LoopResult,
    LoopStatus,
    LoopTransitionReason,
)
from butler.tool_guardrails import ToolCallGuardrailController
from butler.core.interrupt import clear_interrupt, is_interrupted, set_interrupt
from butler.core.steer import clear_steer, mark_run_active, mark_run_inactive
from butler.transport.base import LLMClientProtocol
from butler.transport.fallback import FallbackEntry
from butler.transport.llm_client import LLMClient

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
    emit_skipped_plugin_metric,
    filter_fallback_chain_safe,
    maybe_compact_turn_safe,
    run_after_tools_plugins_safe,
    run_stop_hooks_safe,
)
from butler.core.best_effort import record_best_effort_skip
from butler.core.loop_callbacks_merge import merge_loop_callbacks
from butler.core.loop_plugins import default_plugin_registry
from butler.core.session_transcript import transcript_batch
from butler.execution_context import (
    get_current_orchestrator,
    get_current_session_key,
    use_execution_context,
)
from butler.mcp.turn_scrape_dedup import turn_scrape_dedup_scope
from butler.tools.network_search_policy import turn_network_search_scope

# Import split modules
from butler.core.agent_loop.loop_conversation import (
    _init_turn_state,
    _build_turn_ephemeral_system,
    _update_conversation_state,
)
from butler.core.agent_loop.loop_helpers import (
    _call_llm_with_retry,
    _dispatch_tool,
    _estimate_tokens,
    _interrupt_check,
    _prepare_messages_for_api,
    _prepare_user_message,
    _process_tool_calls,
    _restore_primary_client,
    _tool_execution_context,
    _try_activate_fallback,
)

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
        self._turn_ephemeral_system = _build_turn_ephemeral_system(self, ephemeral_system)
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
                        _update_conversation_state(self, user_message, result)
                        return result
        finally:
            mark_run_inactive(_steer_session)

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
        _init_turn_state(self, steer_session)

        while True:
            state.iteration += 1

            if _interrupt_check(self):
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
