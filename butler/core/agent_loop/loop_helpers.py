"""Loop helpers — utility methods for LLM calls, tool dispatch, and context compression."""

from __future__ import annotations

import logging
from typing import Any, Optional, cast

from butler.core.best_effort import safe_best_effort
from butler.core.context_compressor import compress_messages
from butler.core.llm_retry import call_llm_with_retry
from butler.core.tool_batch import ToolBatchStats, dispatch_tool_with_envelope, process_tool_calls
from butler.core.agent_loop_ops import (
    record_provider_failure_safe,
    run_after_tools_plugins_safe,
)
from butler.execution_context import (
    get_current_orchestrator,
    get_current_session_key,
    use_execution_context,
)
from butler.transport.fallback import create_client_from_entry
from butler.transport.types import NormalizedResponse
from butler.tools.tool_service import get_tool_service

logger = logging.getLogger(__name__)


def _prepare_user_message(
    loop: Any,
    user_message: str,
) -> tuple[str, list[dict[str, Any]]]:
    """Prepare user message with network search if enabled."""
    from butler.tools.network_search_policy import (
        should_run_network_search,
        run_network_search,
    )

    if should_run_network_search(user_message):
        search_results = run_network_search(user_message)
        if search_results:
            loop.diagnostics["network_search_results"] = len(search_results)
            search_context = "\n\n".join([
                f"[搜索结果 {i+1}]: {r['title']}\n{r['summary']}"
                for i, r in enumerate(search_results[:5])
            ])
            enriched_message = f"{user_message}\n\n## 网络搜索结果\n{search_context}"
            return enriched_message, []

    return user_message, []


def _estimate_tokens(loop: Any, messages: list[dict[str, Any]]) -> int:
    """Estimate token count for messages."""
    return sum(len(str(m.get("content", ""))) // 4 for m in messages)


def _prepare_messages_for_api(loop: Any) -> list[dict[str, Any]]:
    """Prepare messages for LLM API call."""
    messages = []

    if loop.system_prompt:
        messages.append({"role": "system", "content": loop.system_prompt})

    if loop._turn_ephemeral_system:
        messages.append({"role": "system", "content": loop._turn_ephemeral_system})

    messages.extend(loop._messages)

    return messages


def _try_activate_fallback(loop: Any) -> bool:
    """Try to activate the next fallback client."""
    if loop._fallback_index >= len(loop._fallback_chain):
        return False

    entry = loop._fallback_chain[loop._fallback_index]
    loop._fallback_index += 1

    try:
        fallback_client = create_client_from_entry(entry)
        loop.client = fallback_client
        loop.diagnostics["fallback_activated"] = entry.model
        logger.info("Activated fallback client: %s", entry.model)
        return True
    except Exception as e:
        logger.error("Failed to activate fallback %s: %s", entry.model, e)
        record_provider_failure_safe(entry.model, str(e))
        return _try_activate_fallback(loop)


def _call_llm_with_retry(loop: Any) -> Optional[NormalizedResponse]:
    """Call LLM with retry logic."""
    messages = _prepare_messages_for_api(loop)

    if _interrupt_check(loop):
        return None

    def _compress_messages(msg: list[dict[str, Any]]) -> list[dict[str, Any]]:
        compressed, _, _ = compress_messages(
            msg,
            max_tokens=loop.config.max_context_tokens,
            diagnostics=loop.diagnostics,
        )
        return cast(list[dict[str, Any]], compressed)

    response, interrupted = call_llm_with_retry(
        client=loop.client,
        config=loop.config,
        callbacks=loop.callbacks,
        tools=loop._turn_tools or loop.tools or [],
        messages=messages,
        diagnostics=loop.diagnostics,
        prepare_messages=lambda: _prepare_messages_for_api(loop),
        compress_messages=_compress_messages,
        interrupt_check=lambda: _interrupt_check(loop),
        try_activate_fallback=lambda: _try_activate_fallback(loop),
        empty_retries=[loop._empty_retries],
    )
    if interrupted:
        return None

    # Emit LLMApiCallEvent for event sourcing
    _emit_llm_api_call_event(loop, response)

    return response


def _emit_llm_api_call_event(loop: Any, response: NormalizedResponse) -> None:
    """Emit LLMApiCallEvent for event sourcing using the new events module."""
    from butler.core.events.event_store import (
        DomainEvent,
        generate_event_id,
        now_utc,
        get_global_event_store,
        get_global_event_bus,
    )

    def _emit() -> None:
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="LLMApiCall",
            session_key=str(loop._session_key or ""),
            timestamp=now_utc(),
            data={
                "provider": str(getattr(loop.client, "provider", "") or ""),
                "model": str(getattr(loop.client, "model", "") or ""),
                "prompt_tokens": getattr(response, "prompt_tokens", 0),
                "completion_tokens": getattr(response, "completion_tokens", 0),
                "duration_ms": getattr(response, "duration_ms", 0),
                "is_streaming": False,
            },
            version=1,
        )

        # Append to event store (append-only persistence)
        store = get_global_event_store()
        store.append(event)

        # Publish to event bus (for real-time subscribers)
        bus = get_global_event_bus()
        bus.publish(event)

    safe_best_effort(_emit, label="agent_loop.llm_api_call_event")


def _process_tool_calls(loop: Any, response: NormalizedResponse) -> ToolBatchStats:
    """Process tool calls from LLM response."""
    if _interrupt_check(loop):
        return ToolBatchStats()

    with _tool_execution_context(loop):
        stats = process_tool_calls(
            response=response,
            messages=_prepare_messages_for_api(loop),
            config=loop.config,
            callbacks=loop.callbacks,
            guardrails=loop._guardrails,
            dispatch_tool=lambda n, a: _dispatch_tool(loop, n, a),
            interrupt_check=lambda: _interrupt_check(loop),
            prefetched=loop._tool_prefetch or None,
        )

    run_after_tools_plugins_safe(loop, stats)
    loop._tool_calls_count += stats.tools_started

    return stats


def _dispatch_tool(loop: Any, name: str, args: dict[str, Any]) -> str:
    """Dispatch a single tool call with event emission."""
    _emit_tool_call_start_event(loop, name, args)

    with _tool_execution_context(loop):
        def _inner(n: str, a: dict[str, Any]) -> str:
            if loop.tool_dispatcher:
                return cast(str, loop.tool_dispatcher(n, a))
            service = get_tool_service()
            return cast(str, service.call_tool(n, a))

        try:
            result = cast(str, dispatch_tool_with_envelope(_inner, name, args))
            _emit_tool_call_complete_event(loop, name, args, result, False)
            return result
        except Exception as exc:
            _emit_tool_call_complete_event(loop, name, args, str(exc), True)
            raise


def _emit_tool_call_start_event(loop: Any, name: str, args: dict[str, Any]) -> None:
    """Emit ToolCallStartedEvent for event sourcing."""
    from butler.core.events.event_store import (
        DomainEvent,
        generate_event_id,
        now_utc,
        get_global_event_store,
        get_global_event_bus,
    )

    def _emit() -> None:
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ToolCallStarted",
            session_key=str(loop._session_key or ""),
            timestamp=now_utc(),
            data={
                "tool_name": name,
                "arguments": args,
            },
            version=1,
        )
        get_global_event_store().append(event)
        get_global_event_bus().publish(event)

    safe_best_effort(_emit, label="agent_loop.tool_call_started")


def _emit_tool_call_complete_event(
    loop: Any, name: str, args: dict[str, Any], result: str, is_error: bool
) -> None:
    """Emit ToolCallCompletedEvent for event sourcing."""
    from butler.core.events.event_store import (
        DomainEvent,
        generate_event_id,
        now_utc,
        get_global_event_store,
        get_global_event_bus,
    )

    def _emit() -> None:
        event = DomainEvent(
            event_id=generate_event_id(),
            event_type="ToolCallCompleted",
            session_key=str(loop._session_key or ""),
            timestamp=now_utc(),
            data={
                "tool_name": name,
                "arguments": args,
                "result": result,
                "is_error": is_error,
            },
            version=1,
        )
        get_global_event_store().append(event)
        get_global_event_bus().publish(event)

    safe_best_effort(_emit, label="agent_loop.tool_call_completed")


def _interrupt_check(loop: Any) -> bool:
    """Check if the loop has been interrupted."""
    from butler.core.interrupt import is_interrupted

    if loop._interrupted:
        return True
    if loop._thread_id is not None and is_interrupted(loop._thread_id):
        loop._interrupted = True
        return True
    return False


def _tool_execution_context(loop: Any) -> Any:
    """Create tool execution context manager."""
    from contextlib import contextmanager
    from collections.abc import Iterator

    @contextmanager
    def _ctx() -> Iterator[None]:
        orch = get_current_orchestrator() or loop._orchestrator
        sk = str(get_current_session_key() or loop._session_key or "")
        role = str(loop._loop_role or "").strip().lower()
        if orch is None and not sk:
            yield
            return
        with use_execution_context(orch, session_key=sk, loop_role=role):
            yield

    return _ctx()


def _restore_primary_client(loop: Any) -> None:
    """Restore primary client after fallback chain exhaustion."""
    if loop._primary_client is not None:
        loop.client = loop._primary_client
        loop._primary_client = None


__all__ = [
    "_prepare_user_message",
    "_estimate_tokens",
    "_prepare_messages_for_api",
    "_try_activate_fallback",
    "_call_llm_with_retry",
    "_emit_llm_api_call_event",
    "_process_tool_calls",
    "_dispatch_tool",
    "_emit_tool_call_start_event",
    "_emit_tool_call_complete_event",
    "_interrupt_check",
    "_tool_execution_context",
    "_restore_primary_client",
]