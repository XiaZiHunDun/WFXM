"""MemoryManager — orchestrates memory providers for the agent core loop.

**Module Boundary Clarification:**
- `memory_manager.py` (core layer): Agent Loop level memory orchestration
  - Multi-provider registration and routing
  - Background sync for non-blocking turn persistence
  - Prefetch coordination across providers
  - Tool routing to the correct provider
  - Session lifecycle management hooks

- `memory/facade.py` (memory layer): Orchestrator level memory service
  - Concrete memory storage implementations (ButlerMemory, ProjectMemory)
  - Memory tool business logic (butler_remember, butler_recall)
  - Direct integration with orchestrator state

**Relationship:**
MemoryManager can register ButlerMemoryService (from facade) as one of its providers.
This allows the Agent Loop to access orchestrator-managed memory while also
supporting external memory providers.

Supports:
  - Background sync for non-blocking turn persistence
  - Multiple memory providers with tool routing
  - Session lifecycle management
  - Streaming context scrubbing for display safety

Inspired by hermes-agent's memory_manager.py design.
"""

from __future__ import annotations

import concurrent.futures
import json
import logging
import threading
from concurrent.futures import Future, ThreadPoolExecutor
from typing import Any, Callable, Dict, List, Optional, Set

from .effects.result import Err, Ok, Result
from .memory_provider import MemoryProvider

logger = logging.getLogger(__name__)

# How long shutdown_all() waits for in-flight background sync/prefetch work
_SYNC_DRAIN_TIMEOUT_S = 5.0
_EXTERNAL_PREFETCH_TIMEOUT_S = 8.0


class MemoryManager:
    """Orchestrates memory providers for the agent.

    Features:
      - Single integration point for all memory operations
      - Background sync to avoid blocking the turn loop
      - Tool routing to the correct provider
      - Session lifecycle management
      - Streaming context scrubbing for display safety
    """

    def __init__(self, *, external_prefetch_timeout: Optional[float] = None) -> None:
        self._providers: List[MemoryProvider] = []
        self._tool_to_provider: Dict[str, MemoryProvider] = {}
        self._has_external: bool = False
        self._external_prefetch_timeout = (
            _EXTERNAL_PREFETCH_TIMEOUT_S
            if external_prefetch_timeout is None
            else float(external_prefetch_timeout)
        )
        # Constructor validation is handled by create_memory_manager factory
        self._external_prefetch_threads: Dict[str, threading.Thread] = {}
        self._external_prefetch_lock = threading.Lock()
        self._sync_executor: Optional[ThreadPoolExecutor] = None
        self._sync_executor_lock = threading.Lock()
        self._background_futures: Dict[Future, str] = {}
        self._shutting_down = False
        self._shutdown_drain_state: Dict[str, Any] = {
            "status": "not_started",
            "abandoned_writes": 0,
            "abandoned_prefetches": 0,
            "active_tasks": 0,
        }


    # -- Registration --------------------------------------------------------

    def add_provider(self, provider: MemoryProvider) -> None:
        """Register a memory provider.

        Built-in provider (name ``"builtin"``) is always accepted.
        Only **one** external (non-builtin) provider is allowed.
        """
        is_builtin = provider.name == "builtin"

        if not is_builtin:
            if self._has_external:
                existing = next(
                    (p.name for p in self._providers if p.name != "builtin"), "unknown"
                )
                logger.warning(
                    "Rejected memory provider '%s' — external provider '%s' is "
                    "already registered. Only one external memory provider is "
                    "allowed at a time.",
                    provider.name, existing,
                )
                return
            self._has_external = True

        self._providers.append(provider)

        # Index tool names -> provider for routing
        for raw_schema in provider.get_tool_schemas():
            schema = self._normalize_tool_schema(raw_schema)
            if schema is None:
                continue
            tool_name = schema["name"]
            if tool_name and tool_name not in self._tool_to_provider:
                self._tool_to_provider[tool_name] = provider
            elif tool_name in self._tool_to_provider:
                logger.warning(
                    "Memory tool name conflict: '%s' already registered by %s, "
                    "ignoring from %s",
                    tool_name,
                    self._tool_to_provider[tool_name].name,
                    provider.name,
                )

        logger.info(
            "Memory provider '%s' registered (%d tools)",
            provider.name,
            len(provider.get_tool_schemas()),
        )

    @property
    def providers(self) -> List[MemoryProvider]:
        """All registered providers in order."""
        return list(self._providers)

    def get_provider(self, name: str) -> Optional[MemoryProvider]:
        """Get a provider by name, or None if not registered."""
        for p in self._providers:
            if p.name == name:
                return p
        return None

    # -- System prompt -------------------------------------------------------

    def build_system_prompt(self) -> str:
        """Collect system prompt blocks from all providers."""
        blocks = []
        for provider in self._providers:
            try:
                block = provider.system_prompt_block()
                if block and block.strip():
                    blocks.append(block)
            except Exception as e:
                logger.warning(
                    "Memory provider '%s' system_prompt_block() failed: %s",
                    provider.name, e,
                )
        return "\n\n".join(blocks)

    # -- Prefetch / recall ---------------------------------------------------

    def prefetch_all(self, query: str, *, session_id: str = "") -> str:
        """Collect prefetch context from all providers."""
        clean_query = query.strip()
        if not clean_query:
            return ""
        parts = []
        for provider in self._providers:
            try:
                result = self._prefetch_provider(provider, clean_query, session_id=session_id)
                if result and result.strip():
                    parts.append(result)
            except Exception as e:
                logger.debug(
                    "Memory provider '%s' prefetch failed (non-fatal): %s",
                    provider.name, e,
                )
        return "\n\n".join(parts)

    def _prefetch_provider(
        self, provider: MemoryProvider, query: str, *, session_id: str = ""
    ) -> str:
        if provider.name == "builtin":
            return provider.prefetch(query, session_id=session_id)

        result_box: Dict[str, str] = {}
        error_box: Dict[str, Exception] = {}

        def _run() -> None:
            try:
                result_box["value"] = provider.prefetch(query, session_id=session_id) or ""
            except Exception as exc:
                error_box["value"] = exc

        thread = threading.Thread(
            target=_run,
            daemon=True,
            name=f"memory-prefetch-{provider.name}",
        )
        with self._external_prefetch_lock:
            existing = self._external_prefetch_threads.get(provider.name)
            if existing is not None:
                if existing.is_alive():
                    logger.debug(
                        "Memory provider '%s' prefetch is still running; skipping this turn",
                        provider.name,
                    )
                    return ""
                self._external_prefetch_threads.pop(provider.name, None)
            self._external_prefetch_threads[provider.name] = thread
            thread.start()

        thread.join(self._external_prefetch_timeout)
        if thread.is_alive():
            logger.warning(
                "Memory provider '%s' prefetch timed out after %.1fs; skipping it",
                provider.name,
                self._external_prefetch_timeout,
            )
            return ""

        with self._external_prefetch_lock:
            if self._external_prefetch_threads.get(provider.name) is thread:
                self._external_prefetch_threads.pop(provider.name, None)
        if error_box:
            raise error_box["value"]
        return result_box.get("value", "")

    def queue_prefetch_all(self, query: str, *, session_id: str = "") -> None:
        """Queue background prefetch on all providers for the next turn."""
        providers = list(self._providers)
        if not providers:
            return

        clean_query = query.strip()
        if not clean_query:
            return

        def _run() -> None:
            for provider in providers:
                try:
                    provider.queue_prefetch(clean_query, session_id=session_id)
                except Exception as e:
                    logger.debug(
                        "Memory provider '%s' queue_prefetch failed (non-fatal): %s",
                        provider.name, e,
                    )

        self._submit_background(_run, kind="prefetch")

    # -- Sync ----------------------------------------------------------------

    def sync_all(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Sync a completed turn to all providers.

        Runs on a background worker thread, NOT inline on the
        turn-completion path to avoid blocking.

        Emits MemorySyncStarted and MemorySyncCompleted events.
        """
        providers = list(self._providers)
        if not providers:
            return

        clean_user_content = user_content.strip()
        if not clean_user_content:
            return

        # Emit memory sync started event
        self._emit_memory_event(
            "MemorySyncStarted",
            {
                "session_id": session_id,
                "user_content_length": len(clean_user_content),
                "assistant_content_length": len(assistant_content),
                "provider_count": len(providers),
            },
        )

        def _run() -> None:
            success_count = 0
            error_count = 0
            for provider in providers:
                try:
                    provider.sync_turn(
                        clean_user_content,
                        assistant_content,
                        session_id=session_id,
                        messages=messages,
                    )
                    success_count += 1
                except Exception as e:
                    error_count += 1
                    logger.warning(
                        "Memory provider '%s' sync_turn failed: %s",
                        provider.name, e,
                    )

            # Emit memory sync completed event
            self._emit_memory_event(
                "MemorySyncCompleted",
                {
                    "session_id": session_id,
                    "success_count": success_count,
                    "error_count": error_count,
                    "total_providers": len(providers),
                },
            )

        self._submit_background(_run)

    # -- Background dispatch -------------------------------------------------

    def _submit_background(self, fn: Callable[[], None], *, kind: str = "write") -> None:
        """Queue ``fn`` on the serialized worker and track its durability class."""
        executor = self._get_sync_executor()
        if executor is None:
            if self._shutting_down:
                logger.warning("Memory manager is shutting down; rejecting late %s task", kind)
                return
            try:
                fn()
            except Exception as e:
                logger.debug("Inline memory background task failed: %s", e)
            return
        try:
            with self._sync_executor_lock:
                if self._shutting_down:
                    logger.warning("Memory manager is shutting down; rejecting late %s task", kind)
                    return
                future = executor.submit(fn)
                self._background_futures[future] = kind
            future.add_done_callback(self._forget_background_future)
        except RuntimeError:
            if self._shutting_down:
                logger.warning("Memory manager shut down during %s submission; task rejected", kind)
                return
            try:
                fn()
            except Exception as e:
                logger.debug("Inline memory background task failed: %s", e)

    def _forget_background_future(self, future: Future) -> None:
        with self._sync_executor_lock:
            self._background_futures.pop(future, None)

    def _get_sync_executor(self) -> Optional[ThreadPoolExecutor]:
        """Lazily create the single-worker background executor."""
        if self._shutting_down:
            return None
        if self._sync_executor is not None:
            return self._sync_executor
        with self._sync_executor_lock:
            if self._shutting_down:
                return None
            if self._sync_executor is None:
                try:
                    self._sync_executor = ThreadPoolExecutor(
                        max_workers=1,
                        thread_name_prefix="mem-sync",
                    )
                except Exception as e:
                    logger.warning("Failed to create memory sync executor: %s", e)
                    return None
            return self._sync_executor

    def flush_pending(self, timeout: Optional[float] = None) -> bool:
        """Block until queued sync/prefetch work has drained."""
        executor = self._sync_executor
        if executor is None:
            return True
        try:
            fut = executor.submit(lambda: None)
        except RuntimeError:
            return True
        try:
            fut.result(timeout=timeout)
            return True
        except Exception:
            return False

    # -- Tools ---------------------------------------------------------------

    @staticmethod
    def _normalize_tool_schema(schema: Any) -> Optional[Dict[str, Any]]:
        """Return a function-tool dict with a resolvable top-level ``name``."""
        if not isinstance(schema, dict):
            return None
        if schema.get("type") == "function" and isinstance(schema.get("function"), dict):
            schema = schema["function"]
            if not isinstance(schema, dict):
                return None
        name = schema.get("name", "")
        if not name or not isinstance(name, str):
            return None
        return schema

    def get_all_tool_schemas(self) -> List[Dict[str, Any]]:
        """Collect tool schemas from all providers."""
        schemas = []
        seen: Set[str] = set()
        for provider in self._providers:
            try:
                for raw_schema in provider.get_tool_schemas():
                    schema = self._normalize_tool_schema(raw_schema)
                    if schema is None:
                        logger.warning(
                            "Memory provider '%s' returned a tool schema with "
                            "no resolvable name; skipping (%r)",
                            provider.name, raw_schema,
                        )
                        continue
                    name = schema["name"]
                    if name not in seen:
                        schemas.append(schema)
                        seen.add(name)
            except Exception as e:
                logger.warning(
                    "Memory provider '%s' get_tool_schemas() failed: %s",
                    provider.name, e,
                )
        return schemas

    def get_all_tool_names(self) -> set:
        """Return set of all tool names across all providers."""
        return set(self._tool_to_provider.keys())

    def has_tool(self, tool_name: str) -> bool:
        """Check if any provider handles this tool."""
        return tool_name in self._tool_to_provider

    def handle_tool_call(
        self, tool_name: str, args: Dict[str, Any], **kwargs
    ) -> str:
        """Route a tool call to the correct provider."""
        provider = self._tool_to_provider.get(tool_name)
        if provider is None:
            return json.dumps({"error": f"No memory provider handles tool '{tool_name}'"})
        try:
            return provider.handle_tool_call(tool_name, args, **kwargs)
        except Exception as e:
            logger.error(
                "Memory provider '%s' handle_tool_call(%s) failed: %s",
                provider.name, tool_name, e,
            )
            return json.dumps({"error": f"Memory tool '{tool_name}' failed: {e}"})

    # -- Lifecycle hooks -----------------------------------------------------

    def on_turn_start(self, turn_number: int, message: str, **kwargs) -> None:
        """Notify all providers of a new turn."""
        for provider in self._providers:
            try:
                provider.on_turn_start(turn_number, message, **kwargs)
            except Exception as e:
                logger.debug(
                    "Memory provider '%s' on_turn_start failed: %s",
                    provider.name, e,
                )

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Notify all providers of session end."""
        for provider in self._providers:
            try:
                provider.on_session_end(messages)
            except Exception as e:
                logger.warning(
                    "Memory provider '%s' on_session_end failed: %s",
                    provider.name, e,
                    exc_info=True,
                )

    def commit_session_boundary_async(
        self,
        messages: List[Dict[str, Any]],
        *,
        new_session_id: str,
        parent_session_id: str = "",
        reason: str = "new_session",
    ) -> None:
        """Queue old-session extraction + provider rebinding as ONE serialized task."""
        if not self._providers:
            return
        snapshot = list(messages or [])

        def _run() -> None:
            try:
                self.on_session_end(snapshot)
            except Exception as e:
                logger.warning("Session-boundary extraction failed: %s", e)
            try:
                self.on_session_switch(
                    new_session_id,
                    parent_session_id=parent_session_id,
                    reset=True,
                    reason=reason,
                )
            except Exception as e:
                logger.warning("Session-boundary switch failed: %s", e)

        self._submit_background(_run)

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs,
    ) -> None:
        """Notify all providers that the agent's session_id has rotated.

        Emits SessionSwitchEvent for event sourcing.
        """
        if not new_session_id:
            return

        # Emit session switch event
        self._emit_memory_event(
            "SessionSwitch",
            {
                "new_session_id": new_session_id,
                "parent_session_id": parent_session_id,
                "reset": reset,
                "reason": kwargs.get("reason", ""),
            },
        )

        for provider in self._providers:
            try:
                provider.on_session_switch(
                    new_session_id,
                    parent_session_id=parent_session_id,
                    reset=reset,
                    **kwargs,
                )
            except Exception as e:
                logger.debug(
                    "Memory provider '%s' on_session_switch failed: %s",
                    provider.name, e,
                )

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Notify all providers before context compression."""
        parts = []
        for provider in self._providers:
            try:
                result = provider.on_pre_compress(messages)
                if result and result.strip():
                    parts.append(result)
            except Exception as e:
                logger.debug(
                    "Memory provider '%s' on_pre_compress failed: %s",
                    provider.name, e,
                )
        return "\n\n".join(parts)

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Notify external providers when memory is written."""
        for provider in self._providers:
            if provider.name == "builtin":
                continue
            try:
                provider.on_memory_write(action, target, content, metadata=metadata)
            except Exception as e:
                logger.debug(
                    "Memory provider '%s' on_memory_write failed: %s",
                    provider.name, e,
                )

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs) -> None:
        """Notify all providers that a subagent completed."""
        for provider in self._providers:
            try:
                provider.on_delegation(
                    task, result, child_session_id=child_session_id, **kwargs
                )
            except Exception as e:
                logger.debug(
                    "Memory provider '%s' on_delegation failed: %s",
                    provider.name, e,
                )

    def shutdown_all(self) -> None:
        """Shut down all providers (reverse order for clean teardown)."""
        self._drain_sync_executor()
        for provider in reversed(self._providers):
            try:
                provider.shutdown()
            except Exception as e:
                logger.warning(
                    "Memory provider '%s' shutdown failed: %s",
                    provider.name, e,
                )

    def _emit_memory_event(self, event_type: str, data: Dict[str, Any]) -> None:
        """Emit a memory management domain event for event sourcing."""
        try:
            from butler.core.events.event_store import (
                DomainEvent,
                generate_event_id,
                now_utc,
                get_global_event_store,
                get_global_event_bus,
            )

            event = DomainEvent(
                event_id=generate_event_id(),
                event_type=event_type,
                session_key=data.get("session_id", ""),
                timestamp=now_utc(),
                data=data,
                version=1,
            )
            get_global_event_store().append(event)
            get_global_event_bus().publish(event)
        except Exception as e:
            logger.debug("Failed to emit memory event: %s", e)

    @property
    def shutdown_drain_state(self) -> Dict[str, Any]:
        """Snapshot of the most recent bounded shutdown drain outcome."""
        with self._sync_executor_lock:
            return dict(self._shutdown_drain_state)

    def _drain_sync_executor(self) -> None:
        """Give queued FIFO work a bounded chance, then abandon explicitly."""
        with self._sync_executor_lock:
            self._shutting_down = True
            executor = self._sync_executor
            self._sync_executor = None
            tracked = dict(self._background_futures)
            self._shutdown_drain_state = {
                "status": "draining" if executor is not None else "drained",
                "abandoned_writes": 0,
                "abandoned_prefetches": 0,
                "active_tasks": sum(not future.done() for future in tracked),
            }
        if executor is None:
            return

        executor.shutdown(wait=False, cancel_futures=False)
        _, pending = concurrent.futures.wait(tuple(tracked), timeout=_SYNC_DRAIN_TIMEOUT_S)
        if not pending:
            with self._sync_executor_lock:
                self._shutdown_drain_state.update(status="drained", active_tasks=0)
            return

        abandoned_writes = 0
        abandoned_prefetches = 0
        active_tasks = 0
        for future in pending:
            kind = tracked[future]
            if future.cancel():
                if kind == "prefetch":
                    abandoned_prefetches += 1
                else:
                    abandoned_writes += 1
            else:
                active_tasks += 1

        with self._sync_executor_lock:
            self._shutdown_drain_state.update(
                status="timed_out",
                abandoned_writes=abandoned_writes,
                abandoned_prefetches=abandoned_prefetches,
                active_tasks=active_tasks,
            )
        logger.warning(
            "Memory shutdown drain timed out after %.2fs; abandoning %d queued "
            "memory write(s) and %d queued prefetch(es); %d active task(s) remain detached",
            _SYNC_DRAIN_TIMEOUT_S,
            abandoned_writes,
            abandoned_prefetches,
            active_tasks,
        )

    def initialize_all(self, session_id: str, **kwargs) -> None:
        """Initialize all providers."""
        for provider in self._providers:
            try:
                provider.initialize(session_id=session_id, **kwargs)
            except Exception as e:
                logger.warning(
                    "Memory provider '%s' initialize failed: %s",
                    provider.name, e,
                )


def create_memory_manager(
    *,
    external_prefetch_timeout: Optional[float] = None,
) -> Result[MemoryManager, ValueError]:
    """Factory function to create a MemoryManager with validation.

    Returns:
        Ok(MemoryManager) if validation passes
        Err(ValueError) if external_prefetch_timeout is invalid
    """
    timeout = (
        _EXTERNAL_PREFETCH_TIMEOUT_S
        if external_prefetch_timeout is None
        else float(external_prefetch_timeout)
    )
    if timeout <= 0:
        return Err(ValueError("external_prefetch_timeout must be positive"))
    return Ok(MemoryManager(external_prefetch_timeout=timeout))


__all__ = ["MemoryManager", "create_memory_manager"]