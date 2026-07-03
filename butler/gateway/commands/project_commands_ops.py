"""Project command status best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def format_owner_status_header_lines_safe(
    orchestrator: Any,
    session_key: str,
) -> list[str]:
    def _run() -> list[str]:
        from butler.gateway.owner_surface import format_owner_status_header

        lines = format_owner_status_header(orchestrator, session_key)
        if not isinstance(lines, list):
            raise ValueError("owner status header must be a list")
        return lines

    result = safe_best_effort(
        _run,
        label="project_commands.owner_status_header",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
