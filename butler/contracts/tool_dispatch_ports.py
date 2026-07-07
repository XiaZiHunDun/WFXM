"""Tool dispatch Protocol — tool_batch without importing tool_dispatch module."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from butler.tool_guardrails import ToolCallGuardrailController


@runtime_checkable
class ToolDispatchPort(Protocol):
    """Single-tool dispatch entry used by ``process_tool_calls``."""

    def dispatch_one_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        tool_call_id: str = "",
        batch_guard: Any = None,
        prefetched: dict[str, str] | None = None,
        guardrails: ToolCallGuardrailController | None = None,
        dispatch_tool: Callable[[str, dict[str, Any]], str],
    ) -> str: ...


__all__ = ["ToolDispatchPort"]
