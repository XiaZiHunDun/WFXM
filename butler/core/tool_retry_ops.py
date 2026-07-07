"""Tool retry classification best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def is_retry_tool_error_safe(result: str) -> bool | None:
    """Return retry classification, or ``None`` when the check path failed."""

    def _run() -> bool:
        from butler.core.tool_error_policy import ToolErrorKind, classify_tool_error

        return bool(classify_tool_error(result) == ToolErrorKind.retry)

    outcome = safe_best_effort(
        _run,
        label="tool_retry.classify_error",
        default=None,
    )
    return bool(outcome) if isinstance(outcome, bool) else None
