"""Outbound completion hooks — outbound_bridge without importing completion_notify."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class OutboundCompletionHooks(Protocol):
    """Delegate / turn / workflow completion pushes (L1 gateway seam)."""

    def flush_pending_delegate_completion(self, bridge: Any) -> bool: ...

    def try_push_agent_report(
        self,
        report: Any,
        *,
        kind: str,
        bridge: Any,
        elapsed_turn_seconds: float,
    ) -> bool: ...

    def try_push_turn_timeout(
        self,
        bridge: Any,
        *,
        timeout_seconds: float,
        elapsed_seconds: float,
    ) -> bool: ...

    def try_push_turn_complete(
        self,
        bridge: Any,
        *,
        elapsed_seconds: float,
    ) -> bool: ...

    def deliver_completion_push(
        self,
        adapter: Any,
        chat_id: str,
        body: str,
        *,
        kind: str,
    ) -> Any: ...

    def delegate_completion_mode(self) -> str: ...

    def delegate_completion_max_each(self) -> int: ...


__all__ = ["OutboundCompletionHooks"]
