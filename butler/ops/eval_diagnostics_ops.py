"""Eval diagnostics health append best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def format_assistant_health_lines_safe() -> list[str]:
    def _run() -> list[str]:
        from butler.ops.assistant_health import format_assistant_health_lines

        lines = format_assistant_health_lines()
        if not isinstance(lines, list):
            raise ValueError("assistant health lines must be a list")
        return lines

    result = safe_best_effort(
        _run,
        label="eval_diagnostics.assistant_health",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
