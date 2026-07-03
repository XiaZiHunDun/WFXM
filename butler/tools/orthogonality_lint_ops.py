"""Orthogonality lint best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)


def toolset_for_safe(name: str) -> str | None:
    def _run() -> str:
        from butler.tools.registry import _REGISTRY

        entry = _REGISTRY.get(name)
        if entry is not None:
            return str(entry.toolset or "default")
        return ""

    result = safe_best_effort(
        _run,
        label="orthogonality_lint.toolset",
        default=None,
    )
    return str(result) if result else None


def embed_tool_text_safe(embedder: Any, text: str) -> list[float] | None:
    def _run() -> list[float]:
        vec = embedder.embed(text)
        return list(vec) if vec is not None else []

    result = safe_best_effort(
        _run,
        label="orthogonality_lint.embed",
        default=None,
    )
    return result if isinstance(result, list) else None


def load_embedder_for_lint_safe() -> tuple[Any | None, str | None]:
    def _run() -> Any:
        from butler.memory.embedding import get_embedder

        return get_embedder()

    embedder = safe_best_effort(
        _run,
        label="orthogonality_lint.embedder",
        default=None,
    )
    if embedder is None:
        return None, "orthogonality lint skipped: embedder unavailable"
    return embedder, None


def load_embedder_for_diagnostics_safe() -> Any | None:
    def _run() -> Any:
        from butler.memory.embedding import get_embedder

        return get_embedder()

    return safe_best_effort(
        _run,
        label="orthogonality_lint.diagnostics_embedder",
        default=None,
    )


def get_builtin_tool_definitions_safe() -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.tools.registry import get_tool_definitions

        return list(get_tool_definitions())

    result = safe_best_effort(
        _run,
        label="orthogonality_lint.builtin_defs",
        default=[],
    )
    return result if isinstance(result, list) else []


def get_mcp_tool_definitions_safe(session_key: str) -> list[dict[str, Any]]:
    def _run() -> list[dict[str, Any]]:
        from butler.mcp.config import mcp_enabled
        from butler.mcp.registry_hook import get_mcp_tool_definitions

        if not mcp_enabled():
            return []
        return list(get_mcp_tool_definitions(session_key))

    result = safe_best_effort(
        _run,
        label="orthogonality_lint.mcp_defs",
        default=[],
    )
    return result if isinstance(result, list) else []
