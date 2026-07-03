"""Subagent tool filter best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def is_mcp_registered_name_safe(name: str) -> bool | None:
    """Return registration bool, or ``None`` when the check path failed."""

    def _run() -> bool:
        from butler.mcp.naming import is_mcp_registered_name

        return bool(is_mcp_registered_name(name))

    result = safe_best_effort(
        _run,
        label="subagent_permissions.mcp_registered",
        default=None,
    )
    return bool(result) if isinstance(result, bool) else None
