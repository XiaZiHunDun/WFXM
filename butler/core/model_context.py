"""Resolve model context window / output limits for context budgeting."""

from __future__ import annotations

from typing import Any, cast


def resolve_max_output_tokens(
    orchestrator: Any,
    *,
    session_key: str = "",
    role: str = "butler",
) -> int | None:
    """Return configured max_tokens for the active loop role, if set."""
    from butler.core.model_context_ops import resolve_max_output_tokens_safe

    return cast(int | None, resolve_max_output_tokens_safe(orchestrator, session_key=session_key, role=role))
