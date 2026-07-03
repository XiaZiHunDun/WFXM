"""Correction intent persistence best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def persist_correction_remember_safe(
    orchestrator: Any,
    content: str,
    *,
    session_key: str = "",
) -> tuple[str | None, str | None]:
    """Return ``(result_text, user_error)``; ``user_error`` set on failure."""
    try:
        from butler.tools.memory_tools import tool_butler_remember
        from butler.execution_context import use_execution_context

        with use_execution_context(orchestrator, session_key=session_key):
            result = tool_butler_remember(
                scope="owner_experience",
                content=content,
                category="correction",
            )
        return str(result), None
    except Exception as exc:
        logger.warning("correction intent remember failed: %s", exc)
        return None, f"纠正意图已识别，但写入失败：{exc}"
