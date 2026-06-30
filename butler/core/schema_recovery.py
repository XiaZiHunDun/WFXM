"""Reactive tool-schema recovery for strict grammar backends."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import logging

from butler.transport.schema_sanitizer import (
    is_schema_grammar_error,
    sanitize_tool_schemas,
    strip_pattern_and_format,
)

logger = logging.getLogger(__name__)


@dataclass
class SchemaRecoveryResult:
    tools: list[dict[str, Any]] | None = None
    stripped: int = 0
    recovered: bool = False
    attempted: bool = False


def recover_schema_after_error(
    error: Exception,
    tools: list[dict[str, Any]] | None,
    *,
    diagnostics: dict[str, Any] | None = None,
) -> SchemaRecoveryResult:
    """Strip grammar-hostile schema keywords when an API error indicates parser failure."""
    if not tools or not is_schema_grammar_error(error):
        return SchemaRecoveryResult()

    sanitized = sanitize_tool_schemas(tools) or []
    stripped_tools, stripped = strip_pattern_and_format(sanitized)
    changed = sanitized != tools
    if not stripped and not changed:
        return SchemaRecoveryResult(
            tools=stripped_tools,
            stripped=0,
            recovered=False,
            attempted=True,
        )

    if diagnostics is not None and stripped:
        diagnostics.update({
            "schema_recovered": True,
            "schema_keywords_stripped": stripped,
        })
    try:
        from butler.ops.retry_buckets import record_recovery_event

        record_recovery_event("schema_recovery")
    except Exception as exc:
        logger.debug("recover schema after error skipped: %s", exc)
    return SchemaRecoveryResult(
        tools=stripped_tools,
        stripped=stripped,
        recovered=True,
        attempted=True,
    )
