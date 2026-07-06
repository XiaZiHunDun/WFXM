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
    from butler.core.system_reminder_ops import build_dynamic_system_reminder_safe

    reminder = build_dynamic_system_reminder_safe()
    if reminder is None:
        return user_content
    if not reminder:
        return user_content
    base = str(user_content or "").strip()
    if base:
        return f"{reminder}\n\n{base}"
    return str(reminder)


__all__ = [
    "maybe_prepend_system_reminder",
    "static_system_reminder_enabled",
    "wrap_system_reminder",
]
