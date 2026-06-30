"""Unified event sink Protocol — transcript, compaction hooks, urgent inbound (ENG-6)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class UrgentInbound:
    """Minimal DTO for urgent inbound pop; core avoids gateway queue types."""

    text: str


@runtime_checkable
class EventsSink(Protocol):
    """Single sink surface for session transcript + compaction side-effects."""

    def record_generic_event(
        self,
        session_key: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None: ...

    def record_tool_action(
        self,
        *,
        session_key: str,
        tool_name: str,
        args_preview: str = "",
        source: str = "",
    ) -> None: ...

    def invoke_hook(self, name: str, **kwargs: Any) -> list[Any]: ...

    def emit_context_compaction(
        self,
        *,
        phase: str,
        thread_id: str = "",
        tokens_before: int = 0,
        tokens_after: int = 0,
        messages_before: int = 0,
        messages_after: int = 0,
        source: str = "context",
        remote: bool = False,
    ) -> None: ...

    def pop_urgent_inbound(self, session_key: str) -> UrgentInbound | None: ...


class NullEventsSink:
    """No-op sink when gateway is not wired (CLI / unit tests)."""

    def record_generic_event(
        self,
        session_key: str,
        event_type: str,
        data: dict[str, Any],
    ) -> None:
        return None

    def record_tool_action(
        self,
        *,
        session_key: str,
        tool_name: str,
        args_preview: str = "",
        source: str = "",
    ) -> None:
        return None

    def invoke_hook(self, name: str, **kwargs: Any) -> list[Any]:
        return []

    def emit_context_compaction(self, **kwargs: Any) -> None:
        return None

    def pop_urgent_inbound(self, session_key: str) -> UrgentInbound | None:
        return None


__all__ = ["EventsSink", "NullEventsSink", "UrgentInbound"]
