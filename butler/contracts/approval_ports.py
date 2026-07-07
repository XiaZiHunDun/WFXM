"""Approval storage Protocol (L7) — unify human_gate / approvals / terminal."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ApprovalStore(Protocol):
    """Session-scoped approval persistence."""

    def save_pending(
        self,
        session_key: str,
        *,
        permission: str,
        tool: str,
        pattern: str,
        reason: str = "",
    ) -> str: ...

    def is_approved(
        self,
        session_key: str,
        *,
        permission: str,
        tool: str,
        pattern: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> bool: ...

    def grant_once(self, session_key: str, *, fingerprint: str = "") -> str | None: ...

    def grant_always(
        self,
        session_key: str,
        *,
        permission: str,
        tool: str = "*",
        pattern: str = "*",
    ) -> str: ...


__all__ = ["ApprovalStore"]
