"""Public AgentLoop dataclasses and status enums."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from butler.transport.types import NormalizedResponse


class LoopStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    TOOL_LIMIT = "tool_limit"
    ERROR = "error"
    INTERRUPTED = "interrupted"


@dataclass
class LoopConfig:
    max_iterations: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    retry_max_delay: float = 30.0
    retry_jitter_ratio: float = 0.25
    max_context_tokens: int = 128000
    stream: bool = True
    enable_guardrails: bool = True
    enable_parallel_tools: bool = True
    fallback_entries: list | None = None
    api_stale_timeout: float = 90.0
    max_empty_content_retries: int = 1
    max_truncation_continues: int = 1


@dataclass
class LoopCallbacks:
    on_llm_start: Optional[Callable[[list[dict]], None]] = None
    on_llm_complete: Optional[Callable[[NormalizedResponse], None]] = None
    on_stream_delta: Optional[Callable[[str], None]] = None
    on_stream_boundary: Optional[Callable[[], None]] = None
    on_tool_start: Optional[Callable[[str, dict], None]] = None
    on_tool_complete: Optional[Callable[[str, str], None]] = None
    on_error: Optional[Callable[[Exception, int], None]] = None
    on_iteration: Optional[Callable[[int, LoopStatus], None]] = None
    on_fallback: Optional[Callable[[str, str], None]] = None
    pre_llm_transform: Optional[Callable[[list[dict]], list[dict]]] = None
    should_continue: Optional[Callable[[int, NormalizedResponse], bool]] = None


@dataclass
class LoopResult:
    status: LoopStatus
    final_response: Optional[str] = None
    reasoning: Optional[str] = None
    messages: list = field(default_factory=list)
    iterations: int = 0
    total_tokens: int = 0
    tool_calls_made: int = 0
    error: Optional[str] = None
    elapsed_seconds: float = 0.0
    diagnostics: dict[str, Any] = field(default_factory=dict)
