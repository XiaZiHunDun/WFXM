"""Prompt assembler best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort


def import_system_reminder_safe() -> Any | None:
    def _run() -> Any:
        from butler.core.system_reminder import wrap_system_reminder

        return wrap_system_reminder

    return safe_best_effort(
        _run,
        label="prompt_assembler.system_reminder_import",
        default=None,
    )


def static_system_reminder_enabled_safe() -> bool:
    def _run() -> bool:
        from butler.core.harness_flags import static_system_reminder_enabled

        return bool(static_system_reminder_enabled())

    result = safe_best_effort(
        _run,
        label="prompt_assembler.static_system_flag",
        default=False,
    )
    return bool(result)
