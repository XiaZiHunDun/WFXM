"""Session lifecycle management with hooks and resource cleanup.

This module provides a unified lifecycle manager for sessions that:
1. Manages the full lifecycle: create → start → turn → end → destroy
2. Supports hooks for each lifecycle event
3. Handles resource cleanup on session destruction
4. Maintains backward compatibility with existing lifecycle functions

The manager calls into existing lifecycle.py functions to avoid breaking changes.
"""

from __future__ import annotations

import logging
from typing import Any, Callable, cast

logger = logging.getLogger(__name__)


class SessionLifecycleManager:
    _instances: dict[str, "SessionLifecycleManager"] = {}

    def __init__(self, session_id: str):
        self._session_id = session_id
        self._state: str = "created"
        self._conversation_state = None
        self._hooks: dict[str, list[Callable[[Any], None]]] = {
            "on_create": [],
            "on_start": [],
            "on_turn": [],
            "on_end": [],
            "on_destroy": [],
        }

    def bind_conversation_state(self, conversation_state) -> None:
        self._conversation_state = conversation_state

    @classmethod
    def get(cls, session_id: str) -> "SessionLifecycleManager":
        if session_id not in cls._instances:
            cls._instances[session_id] = cls(session_id)
        return cls._instances[session_id]

    @classmethod
    def clear(cls, session_id: str) -> None:
        cls._instances.pop(session_id, None)

    def register_hook(self, event: str, hook: Callable[[Any], None]) -> None:
        if event in self._hooks:
            self._hooks[event].append(hook)

    def _fire_hooks(self, event: str, *args: Any) -> None:
        for hook in self._hooks.get(event, []):
            try:
                hook(*args)
            except Exception as exc:
                logger.error("Lifecycle hook error [%s]: %s", event, exc)

    def create(self, orchestrator: Any | None = None) -> None:
        if self._state != "created":
            return
        self._state = "created"
        self._fire_hooks("on_create", orchestrator)

    def start(self, orchestrator: Any | None = None) -> None:
        if self._state != "created":
            return
        self._state = "running"
        self._fire_hooks("on_start", orchestrator)

    def sync_turn(self, orchestrator: Any, user_msg: str = "", assistant_msg: str = "", **kwargs) -> dict[str, Any]:
        if self._state != "running":
            return {}
        from butler.session.lifecycle import sync_turn_memory

        result = sync_turn_memory(orchestrator, user_msg, assistant_msg, **kwargs)
        self._fire_hooks("on_turn", orchestrator)
        return result

    def end(self, orchestrator: Any, agent_loop: Any | None = None, reason: str = "") -> dict[str, Any]:
        if self._state != "running":
            return {}
        from butler.session.post_session_ops import trigger_session_end
        from butler.session.session_resume import save_for_resume

        self._state = "ended"
        result = trigger_session_end(
            orchestrator, agent_loop, session_id=self._session_id, reason=reason
        )

        if self._conversation_state:
            save_for_resume(self._session_id, self._conversation_state, state="ended", reason=reason)

        self._fire_hooks("on_end", orchestrator, result)
        return result

    def destroy(self, orchestrator: Any | None = None) -> None:
        if self._state in ("destroyed", "created"):
            return

        from butler.session.new_session import clear_session_boundary_memory
        from butler.session.session_store import get_session_store

        if orchestrator:
            clear_session_boundary_memory(orchestrator, self._session_id)

        store = get_session_store()
        store.update_state(self._session_id, "destroyed", reason="session destroyed")

        self._state = "destroyed"
        self._fire_hooks("on_destroy", orchestrator)
        self.__class__.clear(self._session_id)

    def get_state(self) -> str:
        return self._state

    def is_running(self) -> bool:
        return self._state == "running"
