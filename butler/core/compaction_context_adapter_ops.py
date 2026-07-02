"""Compaction ACL conversion helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.compaction_ports import LoopCompactionView
from butler.core.best_effort import record_best_effort_skip

logger = logging.getLogger(__name__)

_DEGRADED_FALLBACK = "上下文解析异常，请参考缓存数据"


def _tags_suffix(tags: Any) -> str:
    if not isinstance(tags, list) or not tags:
        return ""
    parts = [str(t).strip() for t in tags if str(t).strip()]
    if not parts:
        return ""
    return f" [标签: {','.join(parts)}]"


def _adapt_known_shape(incoming: Any, *, source: str) -> LoopCompactionView | None:
    if incoming is None:
        return LoopCompactionView(
            content="",
            metadata={"source": source, "acl_shape": "none", "acl_empty": True},
        )
    if isinstance(incoming, LoopCompactionView):
        return incoming
    if isinstance(incoming, str):
        return LoopCompactionView(
            content=incoming.strip(),
            metadata={"source": source, "acl_shape": "str"},
        )
    if not isinstance(incoming, dict):
        return None
    if "raw" in incoming:
        return LoopCompactionView(
            content=str(incoming.get("raw") or "").strip(),
            metadata={"source": source, "acl_shape": "v1_raw"},
        )
    if "summary" in incoming:
        summary = str(incoming.get("summary") or "").strip()
        content = f"{summary}{_tags_suffix(incoming.get('tags'))}"
        return LoopCompactionView(
            content=content,
            metadata={
                "source": source,
                "acl_shape": "v2_summary_tags",
                "tags": incoming.get("tags") if isinstance(incoming.get("tags"), list) else [],
            },
        )
    ctx = incoming.get("additionalContext") or incoming.get("additional_context")
    if ctx is not None:
        if isinstance(ctx, list):
            joined = "\n".join(str(c).strip() for c in ctx if str(c).strip())
        else:
            joined = str(ctx).strip()
        return LoopCompactionView(
            content=joined,
            metadata={"source": source, "acl_shape": "hook_additional_context"},
        )
    return LoopCompactionView(
        content=str(incoming).strip(),
        metadata={"source": source, "acl_shape": "unknown_dict", "acl_warn": "unknown_shape"},
    )


def to_loop_compaction_view_loud(
    incoming: Any,
    *,
    source: str = "unknown",
) -> LoopCompactionView:
    """Convert external compaction payload; never raises to callers."""
    try:
        view = _adapt_known_shape(incoming, source=source)
        if view is not None:
            return view
        return LoopCompactionView(
            content=str(incoming).strip(),
            metadata={"source": source, "acl_shape": "fallback_str", "acl_warn": "unknown_shape"},
        )
    except Exception as exc:
        logger.debug("compaction ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"compaction_acl.{source}", exc)
        from butler.core.metrics_sink import inc

        inc("compaction_acl_degraded", labels={"source": str(source)[:48]})
        return LoopCompactionView(
            content=_DEGRADED_FALLBACK,
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )
