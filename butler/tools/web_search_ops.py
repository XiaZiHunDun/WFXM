"""DuckDuckGo search attempt fail-closed helpers (P0-A)."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def try_search_attempt_safe(
    run: Callable[[], list[dict[str, str]]],
    *,
    kind: str,
    trust_env: bool,
    round_idx: int,
    query: str,
) -> list[dict[str, str]] | None:
    try:
        rows = run()
        if rows:
            return rows
        return None
    except Exception as exc:
        logger.warning(
            "DuckDuckGo %s trust_env=%s round=%s failed: %s",
            kind,
            trust_env,
            round_idx,
            exc,
        )
        return None
