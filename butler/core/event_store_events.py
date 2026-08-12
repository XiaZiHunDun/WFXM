"""Domain event schemas for agent loop operations.

Based on Event Sourcing pattern - session state can be fully reconstructed
from the event stream.

Inspired by DDD and Effect-TS/ZIO event-driven architecture.
"""

from __future__ import annotations

import uuid
from dataclasses import field
from datetime import datetime
from typing import Any

import pydantic

from butler.core.effects.result import Err, Ok, Result


# ── Base Event Models ──


class DomainEvent(pydantic.BaseModel):
    """Base class for all domain events."""

    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str
    session_key: str
    timestamp: float = field(default_factory=lambda: datetime.now().timestamp())
    stored_at: datetime = field(default_factory=lambda: datetime.now())

    model_config = pydantic.ConfigDict(frozen=True)


# ── Tool Call Events ──


class ToolCallEvent(DomainEvent):
    """Event for tool invocation."""

    event_type: str = "tool_call"
    tool_name: str
    args: dict[str, Any]
    args_preview: str = ""
    source: str = ""
    is_delegate: bool = False


class ToolResultEvent(DomainEvent):
    """Event for tool execution result."""

    event_type: str = "tool_result"
    tool_name: str
    success: bool
    result: Any = None
    error: str = ""
    duration_ms: float = 0.0


# ── LLM API Call Events ──


class LLMApiCallEvent(DomainEvent):
    """Event for LLM API invocation."""

    event_type: str = "llm_api_call"
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    duration_ms: float = 0.0
    success: bool = True
    error: str = ""

    @pydantic.model_validator(mode="after")
    def _compute_total_tokens(self) -> "LLMApiCallEvent":
        """Automatically compute total_tokens if not provided."""
        if self.total_tokens == 0 and (self.prompt_tokens > 0 or self.completion_tokens > 0):
            object.__setattr__(self, "total_tokens", self.prompt_tokens + self.completion_tokens)
        return self


class LLMResponseEvent(DomainEvent):
    """Event for LLM response."""

    event_type: str = "llm_response"
    model: str
    content: str
    finish_reason: str = ""
    usage: dict[str, Any] = field(default_factory=dict)


# ── Context Compaction Events ──


class ContextCompactionEvent(DomainEvent):
    """Event for context compaction operation."""

    event_type: str = "context_compaction"
    phase: str
    tokens_before: int = 0
    tokens_after: int = 0
    messages_before: int = 0
    messages_after: int = 0
    source: str = "context"
    remote: bool = False


# ── Session Lifecycle Events ──


class SessionStartEvent(DomainEvent):
    """Event for session start."""

    event_type: str = "session_start"
    platform: str = ""
    chat_id: str = ""
    project_name: str = ""


class SessionEndEvent(DomainEvent):
    """Event for session end."""

    event_type: str = "session_end"
    duration_ms: float = 0.0


# ── Memory Events ──


class MemoryRetrievalEvent(DomainEvent):
    """Event for memory retrieval."""

    event_type: str = "memory_retrieval"
    query: str = ""
    total_returned: int = 0
    relevant_count: int = 0
    used_by_llm: int = 0
    sources: list[str] = field(default_factory=list)


class MemoryWriteEvent(DomainEvent):
    """Event for memory write."""

    event_type: str = "memory_write"
    scope: str = ""
    success: bool = True
    content_chars: int = 0


# ── Delegation Events ──


class DelegateTaskEvent(DomainEvent):
    """Event for delegate task creation."""

    event_type: str = "delegate_task"
    task_id: str = ""
    task_name: str = ""
    priority: str = "normal"


class DelegateCompletedEvent(DomainEvent):
    """Event for delegate task completion."""

    event_type: str = "delegate_completed"
    task_id: str = ""
    success: bool = True
    result: Any = None


class DelegateFailedEvent(DomainEvent):
    """Event for delegate task failure."""

    event_type: str = "delegate_failed"
    task_id: str = ""
    error: str = ""


# ── Factory Functions ──


def create_tool_call_event(
    *,
    session_key: str,
    tool_name: str,
    args: dict[str, Any],
    args_preview: str = "",
    source: str = "",
    is_delegate: bool = False,
) -> ToolCallEvent:
    """Create a tool call event."""
    return ToolCallEvent(
        session_key=session_key,
        tool_name=tool_name,
        args=args,
        args_preview=args_preview,
        source=source,
        is_delegate=is_delegate,
    )


def create_tool_result_event(
    *,
    session_key: str,
    tool_name: str,
    success: bool,
    result: Any = None,
    error: str = "",
    duration_ms: float = 0.0,
) -> ToolResultEvent:
    """Create a tool result event."""
    return ToolResultEvent(
        session_key=session_key,
        tool_name=tool_name,
        success=success,
        result=result,
        error=error,
        duration_ms=duration_ms,
    )


def create_llm_api_call_event(
    *,
    session_key: str,
    model: str,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    total_tokens: int = 0,
    duration_ms: float = 0.0,
    success: bool = True,
    error: str = "",
) -> LLMApiCallEvent:
    """Create an LLM API call event."""
    return LLMApiCallEvent(
        session_key=session_key,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        duration_ms=duration_ms,
        success=success,
        error=error,
    )


def create_llm_response_event(
    *,
    session_key: str,
    model: str,
    content: str,
    finish_reason: str = "",
    usage: dict[str, Any] | None = None,
) -> LLMResponseEvent:
    """Create an LLM response event."""
    return LLMResponseEvent(
        session_key=session_key,
        model=model,
        content=content,
        finish_reason=finish_reason,
        usage=usage or {},
    )


def create_context_compaction_event(
    *,
    session_key: str,
    phase: str,
    tokens_before: int = 0,
    tokens_after: int = 0,
    messages_before: int = 0,
    messages_after: int = 0,
    source: str = "context",
    remote: bool = False,
) -> ContextCompactionEvent:
    """Create a context compaction event."""
    return ContextCompactionEvent(
        session_key=session_key,
        phase=phase,
        tokens_before=tokens_before,
        tokens_after=tokens_after,
        messages_before=messages_before,
        messages_after=messages_after,
        source=source,
        remote=remote,
    )


def create_session_start_event(
    *,
    session_key: str,
    platform: str = "",
    chat_id: str = "",
    project_name: str = "",
) -> SessionStartEvent:
    """Create a session start event."""
    return SessionStartEvent(
        session_key=session_key,
        platform=platform,
        chat_id=chat_id,
        project_name=project_name,
    )


def create_session_end_event(
    *,
    session_key: str,
    duration_ms: float = 0.0,
) -> SessionEndEvent:
    """Create a session end event."""
    return SessionEndEvent(
        session_key=session_key,
        duration_ms=duration_ms,
    )


def create_memory_retrieval_event(
    *,
    session_key: str,
    query: str = "",
    total_returned: int = 0,
    relevant_count: int = 0,
    used_by_llm: int = 0,
    sources: list[str] | None = None,
) -> MemoryRetrievalEvent:
    """Create a memory retrieval event."""
    return MemoryRetrievalEvent(
        session_key=session_key,
        query=query,
        total_returned=total_returned,
        relevant_count=relevant_count,
        used_by_llm=used_by_llm,
        sources=sources or [],
    )


def create_memory_write_event(
    *,
    session_key: str,
    scope: str = "",
    success: bool = True,
    content_chars: int = 0,
) -> MemoryWriteEvent:
    """Create a memory write event."""
    return MemoryWriteEvent(
        session_key=session_key,
        scope=scope,
        success=success,
        content_chars=content_chars,
    )


def create_delegate_task_event(
    *,
    session_key: str,
    task_id: str = "",
    task_name: str = "",
    priority: str = "normal",
) -> DelegateTaskEvent:
    """Create a delegate task event."""
    return DelegateTaskEvent(
        session_key=session_key,
        task_id=task_id,
        task_name=task_name,
        priority=priority,
    )


def create_delegate_completed_event(
    *,
    session_key: str,
    task_id: str = "",
    success: bool = True,
    result: Any = None,
) -> DelegateCompletedEvent:
    """Create a delegate completed event."""
    return DelegateCompletedEvent(
        session_key=session_key,
        task_id=task_id,
        success=success,
        result=result,
    )


def create_delegate_failed_event(
    *,
    session_key: str,
    task_id: str = "",
    error: str = "",
) -> DelegateFailedEvent:
    """Create a delegate failed event."""
    return DelegateFailedEvent(
        session_key=session_key,
        task_id=task_id,
        error=error,
    )


# ── Event Type Registry ──

DOMAIN_EVENT_TYPES = {
    "tool_call": ToolCallEvent,
    "tool_result": ToolResultEvent,
    "llm_api_call": LLMApiCallEvent,
    "llm_response": LLMResponseEvent,
    "context_compaction": ContextCompactionEvent,
    "session_start": SessionStartEvent,
    "session_end": SessionEndEvent,
    "memory_retrieval": MemoryRetrievalEvent,
    "memory_write": MemoryWriteEvent,
    "delegate_task": DelegateTaskEvent,
    "delegate_completed": DelegateCompletedEvent,
    "delegate_failed": DelegateFailedEvent,
}


def deserialize_event(event_type: str, data: dict[str, Any]) -> Result[DomainEvent, ValueError]:
    """Deserialize event data to domain event object."""
    event_class = DOMAIN_EVENT_TYPES.get(event_type)
    if event_class is None:
        return Err(ValueError(f"Unknown event type: {event_type}"))
    try:
        return Ok(event_class(**data))
    except Exception as exc:
        return Err(ValueError(f"Failed to deserialize event: {exc}"))


__all__ = [
    "DomainEvent",
    "ToolCallEvent",
    "ToolResultEvent",
    "LLMApiCallEvent",
    "LLMResponseEvent",
    "ContextCompactionEvent",
    "SessionStartEvent",
    "SessionEndEvent",
    "MemoryRetrievalEvent",
    "MemoryWriteEvent",
    "DelegateTaskEvent",
    "DelegateCompletedEvent",
    "DelegateFailedEvent",
    "create_tool_call_event",
    "create_tool_result_event",
    "create_llm_api_call_event",
    "create_llm_response_event",
    "create_context_compaction_event",
    "create_session_start_event",
    "create_session_end_event",
    "create_memory_retrieval_event",
    "create_memory_write_event",
    "create_delegate_task_event",
    "create_delegate_completed_event",
    "create_delegate_failed_event",
    "DOMAIN_EVENT_TYPES",
    "deserialize_event",
]
