"""API message ACL conversion helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.message_ports import ApiRole, LoopApiMessageView
from butler.core.best_effort import record_best_effort_skip

logger = logging.getLogger(__name__)

_VALID_ROLES = frozenset({"system", "user", "assistant", "tool"})


def _normalize_content(content: Any) -> tuple[str, str]:
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


def to_loop_api_message_view_loud(
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
        role: ApiRole = role_raw
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
        from butler.core.metrics_sink import inc

        inc("api_message_acl_degraded", labels={"source": str(source)[:48]})
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
