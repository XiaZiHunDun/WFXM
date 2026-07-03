"""Interruptible worker thread helpers (P0-A)."""

from __future__ import annotations

from typing import Any, Callable, TypeVar

T = TypeVar("T")


def run_interruptible_worker_safe(
    fn: Callable[[], T],
    result: dict[str, Any],
) -> None:
    try:
        result["value"] = fn()
    except Exception as exc:
        result["error"] = exc
