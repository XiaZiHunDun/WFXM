"""Prompt renderer best-effort helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def static_system_reminder_enabled_safe(*, default: bool = False) -> bool:
    def _run() -> bool:
        from butler.core.harness_flags import static_system_reminder_enabled

        return bool(static_system_reminder_enabled())

    result = safe_best_effort(
        _run,
        label="prompt_renderer.static_reminder_flag",
        default=default,
    )
    return bool(result)
