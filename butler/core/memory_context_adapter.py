"""Anti-corruption adapter: external memory prefetch shapes → LoopMemoryView."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.memory_ports import LoopMemoryView
from butler.core.best_effort import record_best_effort_skip

logger = logging.getLogger(__name__)

_DEGRADED_FALLBACK = ""


def _join_chunks(chunks: Any, *, separator: str = "\n\n") -> str:
    if not isinstance(chunks, list):
        return ""
    parts = [str(c).strip() for c in chunks if str(c).strip()]
    return separator.join(parts)


def _adapt_known_shape(incoming: Any, *, source: str) -> LoopMemoryView | None:
    if incoming is None:
        return LoopMemoryView(
            content="",
            metadata={"source": source, "acl_shape": "none", "acl_empty": True},
        )
    if isinstance(incoming, LoopMemoryView):
        return incoming
    if isinstance(incoming, str):
        return LoopMemoryView(
            content=incoming.strip(),
            metadata={"source": source, "acl_shape": "str"},
        )
    if isinstance(incoming, list):
        content = _join_chunks(incoming)
        return LoopMemoryView(
            content=content,
            metadata={
                "source": source,
                "acl_shape": "list",
                "chunk_count": len(incoming),
            },
        )
    if not isinstance(incoming, dict):
        return None
    for key in ("content", "text", "context", "body"):
        if key in incoming:
            raw = incoming.get(key)
            if isinstance(raw, list):
                content = _join_chunks(raw)
                shape = f"v1_{key}_list"
            else:
                content = str(raw or "").strip()
                shape = f"v1_{key}"
            snippets = incoming.get("snippets")
            meta: dict[str, Any] = {"source": source, "acl_shape": shape}
            if isinstance(snippets, list):
                meta["snippets"] = [str(s)[:200] for s in snippets[:12]]
            return LoopMemoryView(content=content, metadata=meta)
    if "chunks" in incoming or "parts" in incoming:
        key = "chunks" if "chunks" in incoming else "parts"
        content = _join_chunks(incoming.get(key))
        return LoopMemoryView(
            content=content,
            metadata={"source": source, "acl_shape": f"v1_{key}"},
        )
    if "snippets" in incoming and isinstance(incoming.get("snippets"), list):
        content = _join_chunks(incoming.get("snippets"), separator="\n")
        return LoopMemoryView(
            content=content,
            metadata={"source": source, "acl_shape": "v1_snippets"},
        )
    return LoopMemoryView(
        content=str(incoming).strip(),
        metadata={"source": source, "acl_shape": "unknown_dict", "acl_warn": "unknown_shape"},
    )


def to_loop_memory_view(
    incoming: Any,
    *,
    source: str = "memory_prefetch",
) -> LoopMemoryView:
    """Convert external memory payload; never raises to callers."""
    try:
        view = _adapt_known_shape(incoming, source=source)
        if view is not None:
            return view
        return LoopMemoryView(
            content=str(incoming).strip(),
            metadata={"source": source, "acl_shape": "fallback_str", "acl_warn": "unknown_shape"},
        )
    except Exception as exc:
        logger.debug("memory ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"memory_acl.{source}", exc)
        try:
            from butler.core.metrics_sink import inc

            inc("memory_acl_degraded", labels={"source": str(source)[:48]})
        except Exception:
            pass
        return LoopMemoryView(
            content=_DEGRADED_FALLBACK,
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )


def apply_memory_view_to_diagnostics(
    view: LoopMemoryView,
    diagnostics: dict[str, Any] | None,
) -> None:
    """Record ACL observability fields on turn diagnostics."""
    if not isinstance(diagnostics, dict):
        return
    diagnostics["memory_view_version"] = view.schema_version
    shape = view.metadata.get("acl_shape")
    if shape:
        diagnostics["memory_acl_shape"] = shape
    if view.metadata.get("acl_warn") or view.metadata.get("acl_degraded"):
        diagnostics["memory_acl_degraded"] = True


def adapt_memory_prefetch_content(
    incoming: Any,
    *,
    source: str = "memory_prefetch",
    diagnostics: dict[str, Any] | None = None,
) -> str:
    """Single entry: external memory → ACL view → injection string."""
    view = to_loop_memory_view(incoming, source=source)
    apply_memory_view_to_diagnostics(view, diagnostics)
    return view.content
