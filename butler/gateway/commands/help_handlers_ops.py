"""Best-effort help registry lookup (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def format_registry_help_safe(topic: str) -> str | None:
    def _run() -> str | None:
        from butler.gateway.command_registry import format_registry_help

        result = format_registry_help(topic)
        if result.startswith("未找到"):
            return None
        return result

    return safe_best_effort(
        _run,
        label="help_handlers.registry_help",
        default=None,
    )
