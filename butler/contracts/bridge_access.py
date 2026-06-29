"""Outbound bridge access Protocol — tools resolve bridge without importing gateway."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class BridgeAccess(Protocol):
    """Resolve thread-local outbound bridge + workflow failure pushes."""

    def get_optional_bridge(self) -> Any: ...

    def try_push_workflow_failure(
        self,
        workflow_name: str,
        error: Exception | str,
        *,
        session_key: str = "",
    ) -> bool: ...


__all__ = ["BridgeAccess"]
