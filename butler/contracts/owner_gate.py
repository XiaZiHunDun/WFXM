"""Owner gate Protocol — tools/core check via registry, gateway implements."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class OwnerGate(Protocol):
    """Minimal owner-only surface for gateway / tool permission checks."""

    def is_gateway_owner(
        self,
        *,
        platform: str,
        external_id: str | None = None,
        session_key: str = "",
    ) -> bool: ...

    def owner_required_message(self) -> str: ...


__all__ = ["OwnerGate"]
