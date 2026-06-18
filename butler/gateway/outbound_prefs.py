"""Per-reply WeChat outbound preferences (slash commands → single bubble)."""

from __future__ import annotations

from contextvars import ContextVar

_single_bubble_reply: ContextVar[bool] = ContextVar(
    "gateway_single_bubble_reply",
    default=False,
)


def mark_slash_reply_single_bubble() -> None:
    """Next main outbound text should stay one WeChat bubble when possible."""
    _single_bubble_reply.set(True)


def consume_single_bubble_reply() -> bool:
    """Read and clear single-bubble flag (one-shot)."""
    flag = bool(_single_bubble_reply.get())
    if flag:
        _single_bubble_reply.set(False)
    return flag


__all__ = ["consume_single_bubble_reply", "mark_slash_reply_single_bubble"]
