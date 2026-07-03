"""Proactive tool-schema optimization before LLM calls (support line E)."""

from __future__ import annotations

from typing import Any

from butler.env_parse import env_truthy


def schema_optimize_enabled() -> bool:
    return env_truthy("BUTLER_SCHEMA_OPTIMIZE", default=True)


def optimize_tool_definitions(
    tools: list[dict] | None,
    *,
    diagnostics: dict[str, Any] | None = None,
    provider: str = "",
) -> list[dict] | None:
    """Sanitize schemas up-front to reduce grammar 400 errors."""
    if not tools or not schema_optimize_enabled():
        return tools
    from butler.core.schema_optimizer_ops import load_schema_sanitizer_safe

    sanitizer = load_schema_sanitizer_safe()
    if sanitizer is None:
        return tools
    sanitize_tool_schemas, strip_pattern_and_format = sanitizer

    sanitized = sanitize_tool_schemas(tools) or []
    stripped, count = strip_pattern_and_format(sanitized)
    if diagnostics is not None and count:
        diagnostics["schema_optimize_stripped"] = int(count)
        diagnostics["schema_optimize_provider"] = str(provider or "")[:32]
    return stripped or sanitized


__all__ = ["optimize_tool_definitions", "schema_optimize_enabled"]
