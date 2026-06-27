"""Event sink Protocol — core writes, gateway implements (P1-D)."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class EventsSink(Protocol):
    """Minimal event surface for session transcript + tool audit hooks."""

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


__all__ = ["EventsSink"]
