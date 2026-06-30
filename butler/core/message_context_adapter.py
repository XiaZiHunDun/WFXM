"""Anti-corruption adapter: raw message dicts → LoopApiMessageView (API boundary subset)."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.message_ports import ApiRole, LoopApiMessageView
from butler.core.best_effort import record_best_effort_skip
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_VALID_ROLES = frozenset({"system", "user", "assistant", "tool"})


def api_message_acl_enabled() -> bool:
    return env_truthy("BUTLER_API_MESSAGE_ACL", default=False)


def _normalize_content(content: Any) -> tuple[str, str]:
    """Return (text, acl_shape)."""
    if content is None:
        return "", "empty"
    if isinstance(content, str):
        return content, "str"
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                btype = block.get("type")
                if btype == "text":
                    parts.append(str(block.get("text") or ""))
                elif btype in ("thinking", "redacted_thinking"):
                    parts.append(str(block.get("thinking") or block.get("text") or ""))
                else:
                    parts.append(str(block))
            else:
                parts.append(str(block))
        joined = "\n".join(p for p in parts if p.strip())
        return joined, "list_blocks"
    return str(content), "coerced"


def to_loop_api_message_view(
    incoming: dict[str, Any] | LoopApiMessageView,
    *,
    source: str = "api_boundary",
    index: int = -1,
) -> LoopApiMessageView:
    """Convert one message dict; never raises to callers."""
    if isinstance(incoming, LoopApiMessageView):
        return incoming
    try:
        if not isinstance(incoming, dict):
            raise TypeError(f"expected dict, got {type(incoming).__name__}")
        role_raw = str(incoming.get("role") or "").strip()
        if role_raw not in _VALID_ROLES:
            raise ValueError(f"invalid role: {role_raw!r}")
        role: ApiRole = role_raw  # type: ignore[assignment]
        text, shape = _normalize_content(incoming.get("content"))
        meta: dict[str, Any] = {"source": source, "acl_shape": shape}
        if index >= 0:
            meta["index"] = index
        if incoming.get("tool_calls"):
            meta["has_tool_calls"] = True
        if incoming.get("tool_call_id"):
            meta["tool_call_id"] = str(incoming.get("tool_call_id") or "")[:64]
        return LoopApiMessageView(role=role, content=text, metadata=meta)
    except Exception as exc:
        logger.debug("api message ACL adapt failed (%s[%s]): %s", source, index, exc)
        record_best_effort_skip(f"api_message_acl.{source}", exc)
        try:
            from butler.core.metrics_sink import inc

            inc("api_message_acl_degraded", labels={"source": str(source)[:48]})
        except Exception:
            pass
        return LoopApiMessageView(
            role="user",
            content="",
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
                "index": index,
            },
        )


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
