"""Abstract base class for LLM transports and client protocol."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional, Protocol, runtime_checkable

from butler.transport.types import NormalizedResponse


class ProviderTransport(ABC):
    """Protocol adapter between Butler and a specific LLM API format."""

    @property
    @abstractmethod
    def api_mode(self) -> str: ...

    def convert_messages(
        self, messages: List[Dict[str, Any]], **kwargs
    ) -> Any:
        return messages

    def convert_tools(self, tools: List[Dict[str, Any]]) -> Any:
        return tools

    @abstractmethod
    def build_kwargs(
        self,
        model: str,
        messages: Any,
        tools: Optional[Any] = None,
        **params,
    ) -> Dict[str, Any]: ...

    @abstractmethod
    def normalize_response(
        self, response: Any, **kwargs
    ) -> NormalizedResponse: ...

    def validate_response(self, response: Any) -> bool:
        return True

    def extract_cache_stats(self, response: Any) -> Optional[Dict[str, int]]:
        return None

    def map_finish_reason(self, raw_reason: str) -> str:
        return raw_reason


# ---------------------------------------------------------------------------
# LLM client protocol — structural interface for AgentLoop decoupling
# ---------------------------------------------------------------------------


@runtime_checkable
class LLMClientProtocol(Protocol):
    """Minimal interface that AgentLoop requires from an LLM client.

    ``LLMClient`` satisfies this protocol automatically via structural
    subtyping — no explicit inheritance needed.
    """

    provider_name: str
    model: str
    max_tokens: Optional[int]
    temperature: Optional[float]
    timeout: int

    def complete(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        stale_timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> NormalizedResponse: ...

    def stream(
        self,
        messages: list[dict],
        tools: Optional[list[dict]] = None,
        on_delta: Optional[Callable[[str], None]] = None,
        on_tool_call_ready: Optional[Callable[[int, str, str, dict], None]] = None,
        check_interrupt: Optional[Callable[[], bool]] = None,
        stale_timeout: Optional[float] = None,
        **kwargs: Any,
    ) -> NormalizedResponse: ...
