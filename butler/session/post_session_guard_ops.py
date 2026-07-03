"""Post-session guard best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any, Callable


def guard_post_session_safe(
    fn: Callable[[], dict[str, Any]],
    *,
    error_result_fn: Callable[[BaseException], dict[str, Any]],
) -> dict[str, Any]:
    try:
        return fn()
    except Exception as exc:
        return error_result_fn(exc)
