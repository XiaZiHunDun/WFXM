"""Layered post-session extract best-effort helpers (P0-A)."""

from __future__ import annotations

import inspect
import logging
from typing import Any, Awaitable, Callable

from butler.core.best_effort import async_safe_best_effort

logger = logging.getLogger(__name__)


async def run_layered_llm_extract_safe(
    llm_call: Callable[[str], Any | Awaitable[Any]],
    prompt: str,
    *,
    parse_json: Callable[[str], dict[str, Any]],
) -> dict[str, Any] | None:
    async def _run() -> dict[str, Any]:
        raw = llm_call(prompt)
        if inspect.isawaitable(raw):
            raw = await raw
        data = parse_json(str(raw or ""))
        if not isinstance(data, dict):
            raise ValueError("layered extract response is not a dict")
        return data

    return await async_safe_best_effort(
        _run,
        label="post_session_layered.extract",
        default=None,
    )
