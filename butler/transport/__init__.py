"""Butler LLM Transport Layer.

Thin abstraction over LLM provider APIs. Each transport handles
request building and response normalization for one protocol family.

Supported api_modes:
  - chat_completions   (OpenAI-compatible)
  - anthropic_messages  (Anthropic / MiniMax)

Registry pattern: transports self-register at import time via
``register_transport(api_mode, cls)``.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, Type

from butler.transport.types import (  # noqa: F401 — re-export
    NormalizedResponse,
    ToolCall,
    Usage,
    build_tool_call,
)

logger = logging.getLogger(__name__)

_REGISTRY: Dict[str, Type[Any]] = {}
_discovered = False


def register_transport(api_mode: str, transport_cls: type) -> None:
    _REGISTRY[api_mode] = transport_cls


def get_transport(api_mode: str) -> Any:
    global _discovered
    if not _discovered:
        _discover()
    cls = _REGISTRY.get(api_mode)
    if cls is None:
        return None
    return cls()


def _discover() -> None:
    global _discovered
    _discovered = True
    for mod in ("butler.transport.chat_completions", "butler.transport.anthropic_transport"):
        try:
            __import__(mod)
        except ImportError as e:
            logger.debug("Transport %s not available: %s", mod, e)


def list_transports() -> list[str]:
    if not _discovered:
        _discover()
    return list(_REGISTRY.keys())
