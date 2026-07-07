"""Default ApprovalStore — wraps permissions/approvals (L7)."""

from __future__ import annotations

import time
from typing import Any

from butler.contracts.approval_registry import set_approval_store
from butler.permissions.approvals import (
    ApprovalRequest,
    clear_pending,
    grant_always,
    grant_once,
    is_approved,
    once_ttl_seconds,
    save_pending,
)


class PermissionsApprovalStore:
    def save_pending(
        self,
        session_key: str,
        *,
        permission: str,
        tool: str,
        pattern: str,
        reason: str = "",
    ) -> str:
        req = ApprovalRequest(
            permission=permission,
            tool=tool,
            pattern=pattern,
            reason=reason,
        )
        return save_pending(session_key, req)

    def is_approved(
        self,
        session_key: str,
        *,
        permission: str,
        tool: str,
        pattern: str,
        diagnostics: dict[str, Any] | None = None,
    ) -> bool:
        req = ApprovalRequest(
            permission=permission,
            tool=tool,
            pattern=pattern,
        )
        return is_approved(session_key, req, diagnostics=diagnostics)

    def grant_once(self, session_key: str, *, fingerprint: str = "") -> str | None:
        return grant_once(session_key, fingerprint=fingerprint)

    def grant_always(
        self,
        session_key: str,
        *,
        permission: str,
        tool: str = "*",
        pattern: str = "*",
    ) -> str:
        return grant_always(
            session_key,
            permission=permission,
            tool=tool,
            pattern=pattern,
        )


def grant_terminal_exec_once(
    session_key: str,
    *,
    fingerprint: str,
    command: str = "",
    ttl_sec: float | None = None,
) -> None:
    """Record terminal exec approval in unified approvals.json."""
    from butler.permissions.approvals import _load, _purge_once, _save

    sk = str(session_key or "").strip()
    fp = str(fingerprint or "").strip()
    if not sk or not fp:
        return
    data = _load(sk)
    data["once"] = _purge_once(data.get("once") or [])
    data["once"].append(
        {
            "permission": "terminal_exec",
            "tool": "terminal",
            "pattern": fp,
            "fingerprint": fp,
            "command": str(command or "").strip()[:500],
            "expires_at": time.time() + (ttl_sec if ttl_sec is not None else once_ttl_seconds()),
        }
    )
    data["pending"] = None
    _save(sk, data)


def register_default_approval_store() -> None:
    set_approval_store(PermissionsApprovalStore())


register_default_approval_store()

__all__ = [
    "PermissionsApprovalStore",
    "grant_terminal_exec_once",
    "register_default_approval_store",
]
