"""Stdio MCP client best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import async_safe_best_effort

logger = logging.getLogger(__name__)


async def close_stdio_session_safe(session: Any) -> None:
    async def _run() -> None:
        await session.__aexit__(None, None, None)

    await async_safe_best_effort(
        _run,
        label="client_stdio.session_close",
        default=None,
    )


async def close_stdio_transport_safe(transport: Any) -> None:
    async def _run() -> None:
        await transport.__aexit__(None, None, None)

    await async_safe_best_effort(
        _run,
        label="client_stdio.transport_close",
        default=None,
    )


def json_dumps_mcp_result_safe(result: Any) -> str:
    import json

    try:
        if hasattr(result, "model_dump"):
            return json.dumps(result.model_dump(), ensure_ascii=False, default=str)
    except Exception as exc:
        logger.debug("json dumps result skipped: %s", exc)
    return str(result)
