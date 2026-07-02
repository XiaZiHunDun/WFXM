"""Anti-corruption adapter: raw message dicts → LoopApiMessageView (API boundary subset)."""

from __future__ import annotations

from typing import Any

from butler.contracts.message_ports import LoopApiMessageView
from butler.env_parse import env_truthy


def api_message_acl_enabled() -> bool:
    return env_truthy("BUTLER_API_MESSAGE_ACL", default=False)


def to_loop_api_message_view(
    incoming: dict[str, Any] | LoopApiMessageView,
    *,
    source: str = "api_boundary",
    index: int = -1,
) -> LoopApiMessageView:
    """Convert one message dict; never raises to callers."""
    from butler.core.message_context_adapter_ops import to_loop_api_message_view_loud

    return to_loop_api_message_view_loud(incoming, source=source, index=index)


def annotate_api_message_boundary(
    messages: list[dict],
    diagnostics: dict[str, Any] | None,
    *,
    source: str = "prepare_messages",
) -> None:
    """Opt-in boundary check: validate representability; record diagnostics only."""
    if not api_message_acl_enabled() or not messages:
        return
    degraded = 0
    shapes: list[str] = []
    for idx, msg in enumerate(messages):
        view = to_loop_api_message_view(msg, source=source, index=idx)
        shape = str(view.metadata.get("acl_shape") or "")
        if shape:
            shapes.append(shape)
        if view.metadata.get("acl_degraded"):
            degraded += 1
    if not isinstance(diagnostics, dict):
        return
    diagnostics["api_message_acl_checked"] = True
    diagnostics["api_message_acl_count"] = len(messages)
    if degraded:
        diagnostics["api_message_acl_degraded"] = True
        diagnostics["api_message_acl_degraded_count"] = degraded
    if shapes:
        diagnostics["api_message_acl_shapes"] = shapes[:24]
