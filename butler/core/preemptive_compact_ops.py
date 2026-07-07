from typing import Any
"""Preemptive compact pipeline best-effort helpers (P0-A)."""

from __future__ import annotations

from collections.abc import Callable

from butler.core.best_effort import safe_best_effort


def try_preemptive_compress_safe(
    compress: Callable[[list[dict[str, Any]]], list[dict[str, Any]]],
    messages: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool]:
    """Return compressed messages and whether compression succeeded."""

    def _run() -> list[dict[str, Any]]:
        return list(compress(list(messages)))

    result = safe_best_effort(
        _run,
        label="preemptive_compact.compress",
        default=None,
    )
    if isinstance(result, list):
        return result, True
    return list(messages), False


def record_preemptive_truncate_recovery_safe() -> None:
    def _run() -> None:
        from butler.ops.retry_buckets import record_recovery_event

        record_recovery_event("preemptive_truncate")

    safe_best_effort(_run, label="preemptive_compact.truncate_recovery", default=None)
