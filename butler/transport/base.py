"""Abstract base class for LLM transports."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

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
