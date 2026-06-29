"""Gateway wiring for :class:`butler.contracts` OwnerGate + BridgeAccess (R1 续)."""

from __future__ import annotations


def register_gateway_contracts() -> None:
    """Wire contracts registries to live gateway owner/bridge helpers (idempotent)."""
    from butler.contracts.gateway_registry import (
        get_bridge_access,
        get_owner_gate,
        set_bridge_access,
        set_owner_gate,
    )

    if get_owner_gate() is not None and get_bridge_access() is not None:
        return

    from butler.gateway.completion_notify import try_push_workflow_failure
    from butler.gateway.outbound_bridge import get_gateway_bridge_optional
    from butler.gateway.owner_gate import is_gateway_owner, owner_required_message

    class _GatewayOwnerGate:
        def is_gateway_owner(
            self,
            *,
            platform: str,
            external_id: str | None = None,
            session_key: str = "",
        ) -> bool:
            return is_gateway_owner(
                platform=platform,
                external_id=external_id,
                session_key=session_key,
            )

        def owner_required_message(self) -> str:
            return owner_required_message()

    class _GatewayBridgeAccess:
        def get_optional_bridge(self):
            return get_gateway_bridge_optional()

        def try_push_workflow_failure(
            self,
            workflow_name: str,
            error: Exception | str,
            *,
            session_key: str = "",
        ) -> bool:
            bridge = self.get_optional_bridge()
            return try_push_workflow_failure(
                bridge,
                workflow_name,
                error,
                session_key=session_key,
            )

    if get_owner_gate() is None:
        set_owner_gate(_GatewayOwnerGate())
    if get_bridge_access() is None:
        set_bridge_access(_GatewayBridgeAccess())


__all__ = ["register_gateway_contracts"]
