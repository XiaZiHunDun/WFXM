"""Per-reply WeChat outbound preferences (slash commands → single bubble)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Any

_single_bubble_reply: ContextVar[bool] = ContextVar(
    "gateway_single_bubble_reply",
    default=False,
)


def mark_slash_reply_single_bubble() -> None:
    """Next main outbound text should stay one WeChat bubble when possible."""
    try:
        from butler.execution_context import get_current_turn_bridge

        bridge = get_current_turn_bridge()
        if bridge is not None:
            bridge.slash_single_bubble = True
            return
    except Exception:
        pass
    _single_bubble_reply.set(True)


def consume_single_bubble_reply(*, bridge: Any | None = None) -> bool:
    """Read and clear single-bubble flag (one-shot)."""
    if bridge is not None and bool(getattr(bridge, "slash_single_bubble", False)):
        bridge.slash_single_bubble = False
        return True
    flag = bool(_single_bubble_reply.get())
    if flag:
        _single_bubble_reply.set(False)
    return flag


def pop_single_bubble_from_metadata(metadata: dict[str, Any] | None) -> bool:
    """Consume force_single_bubble passed from ``base.handle_message``."""
    if not metadata:
        return consume_single_bubble_reply()
    if metadata.pop("force_single_bubble", False):
        return True
    return consume_single_bubble_reply()


__all__ = [
    "consume_single_bubble_reply",
    "mark_slash_reply_single_bubble",
    "pop_single_bubble_from_metadata",
]
