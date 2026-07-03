"""HTTP MCP client cleanup best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import async_safe_best_effort


async def close_http_session_safe(session: Any) -> None:
    async def _run() -> None:
        await session.__aexit__(None, None, None)

    await async_safe_best_effort(
        _run,
        label="client_http.session_close",
        default=None,
    )


async def close_http_transport_safe(transport: Any) -> None:
    async def _run() -> None:
        await transport.__aexit__(None, None, None)

    await async_safe_best_effort(
        _run,
        label="client_http.transport_close",
        default=None,
    )
