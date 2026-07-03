"""Delegate loop interrupt best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def interrupt_delegate_loop_safe(loop: Any) -> bool:
    def _run() -> bool:
        if hasattr(loop, "interrupt"):
            loop.interrupt()
            return True
        return False

    result = safe_best_effort(
        _run,
        label="delegate_registry.interrupt",
        default=False,
    )
    return bool(result)
