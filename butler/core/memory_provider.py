"""MemoryProvider interface — abstract base class for memory providers."""

from __future__ import annotations

from typing import Any, Dict, List, Optional


class MemoryProvider:
    """Abstract base class for memory providers."""

    @property
    def name(self) -> str:
        """Short identifier for this provider."""
        raise NotImplementedError

    def initialize(self, session_id: str, **kwargs: Any) -> None:
        """Initialize the provider with session context."""

    def system_prompt_block(self) -> str:
        """Return system prompt block for this provider."""
        return ""

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        """Return prefetched context for the given query."""
        return ""

    def queue_prefetch(self, query: str, *, session_id: str = "") -> None:
        """Queue background prefetch for the next turn."""

    def sync_turn(
        self,
        user_content: str,
        assistant_content: str,
        *,
        session_id: str = "",
        messages: Optional[List[Dict[str, Any]]] = None,
    ) -> None:
        """Sync a completed turn to the provider."""

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        """Return tool schemas this provider exposes."""
        return []

    def handle_tool_call(self, name: str, args: Dict[str, Any], **kwargs: Any) -> str:
        """Handle a tool call from the agent."""
        import json

        return json.dumps({"error": f"Unknown memory tool: {name}"})

    def on_turn_start(self, turn_number: int, message: str, **kwargs: Any) -> None:
        """Notify provider of a new turn."""

    def on_session_end(self, messages: List[Dict[str, Any]]) -> None:
        """Notify provider of session end."""

    def on_session_switch(
        self,
        new_session_id: str,
        *,
        parent_session_id: str = "",
        reset: bool = False,
        **kwargs: Any,
    ) -> None:
        """Notify provider that session_id has rotated."""

    def on_pre_compress(self, messages: List[Dict[str, Any]]) -> str:
        """Notify provider before context compression."""
        return ""

    def on_memory_write(
        self,
        action: str,
        target: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Notify provider when memory is written."""

    def on_delegation(self, task: str, result: str, *,
                      child_session_id: str = "", **kwargs: Any) -> None:
        """Notify provider that a subagent completed."""

    def shutdown(self) -> None:
        """Shut down the provider."""


__all__ = ["MemoryProvider"]
