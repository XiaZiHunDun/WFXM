"""Thin Hermes ``MemoryProvider`` adapter around ``ButlerMemoryService``.

Keeps ``butler/`` free of ``agent.*`` imports; only loaded when Hermes Gateway runs.
"""

from __future__ import annotations

from typing import Any, Dict, List

from agent.memory_provider import MemoryProvider

from butler.memory_plugin import ButlerMemoryService


class HermesButlerMemoryProvider(MemoryProvider):
    """Delegates to Butler memory; satisfies Hermes plugin registration."""

    def __init__(self) -> None:
        self._svc = ButlerMemoryService()

    @property
    def name(self) -> str:
        return self._svc.name

    def is_available(self) -> bool:
        return self._svc.is_available()

    def initialize(self, session_id: str, **kwargs) -> None:
        self._svc.initialize(session_id, **kwargs)

    def system_prompt_block(self) -> str:
        return self._svc.system_prompt_block()

    def prefetch(self, query: str, *, session_id: str = "") -> str:
        return self._svc.prefetch(query, session_id=session_id)

    def sync_turn(self, user_content: str, assistant_content: str, *, session_id: str = "") -> None:
        self._svc.sync_turn(user_content, assistant_content, session_id=session_id)

    def get_tool_schemas(self) -> List[Dict[str, Any]]:
        return self._svc.get_tool_schemas()

    def handle_tool_call(self, tool_name: str, args: Dict[str, Any], **kwargs) -> str:
        return self._svc.handle_tool_call(tool_name, args, **kwargs)

    def on_session_switch(self, new_session_id: str, **kwargs) -> None:
        self._svc.on_session_switch(new_session_id, **kwargs)
