"""Static system + dynamic system-reminder blocks (PR-X4 / 主线 L)."""

from __future__ import annotations

from butler.core.harness_flags import static_system_reminder_enabled

_REMINDER_OPEN = "<system-reminder>"
_REMINDER_CLOSE = "</system-reminder>"


def wrap_system_reminder(body: str) -> str:
    text = str(body or "").strip()
    if not text:
        return ""
    return f"{_REMINDER_OPEN}\n{text}\n{_REMINDER_CLOSE}"


def maybe_prepend_system_reminder(user_content: str) -> str:
    """Inject dynamic orchestrator context into the user turn when enabled."""
    if not static_system_reminder_enabled():
        return user_content
    try:
        from butler.execution_context import get_current_orchestrator

        orch = get_current_orchestrator()
        if orch is None:
            return user_content
        reminder = orch.build_dynamic_system_reminder()
    except Exception:
        return user_content
    if not reminder:
        return user_content
    base = str(user_content or "").strip()
    if base:
        return f"{reminder}\n\n{base}"
    return reminder


__all__ = [
    "maybe_prepend_system_reminder",
    "static_system_reminder_enabled",
    "wrap_system_reminder",
]
