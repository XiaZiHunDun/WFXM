"""DAG node router best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any, Callable


def run_node_router_safe(
    router: Callable[[Any], str | None],
    result: Any,
) -> tuple[str | None, str | None]:
    """Return ``(next_id, error_message)``; ``error_message`` set on router failure."""
    try:
        next_id = router(result)
        return (str(next_id) if next_id else None), None
    except Exception as exc:
        return None, str(exc)
