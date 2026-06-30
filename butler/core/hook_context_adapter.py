"""Anti-corruption adapter: external hook shapes → HookContextView."""

from __future__ import annotations

import logging
from typing import Any

from butler.contracts.hook_context_ports import HookContextView
from butler.core.best_effort import record_best_effort_skip
from butler.core.compaction_context_adapter import to_loop_compaction_view

logger = logging.getLogger(__name__)

_DEGRADED_FALLBACK = "Hook 上下文解析异常，已忽略该片段"


def to_hook_context_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> HookContextView:
    """Convert external hook payload; never raises to callers."""
    try:
        compact = to_loop_compaction_view(incoming, source=source)
        meta = dict(compact.metadata)
        meta["acl_domain"] = "hook"
        return HookContextView(
            content=compact.content,
            schema_version=compact.schema_version,
            metadata=meta,
        )
    except Exception as exc:
        logger.debug("hook ACL adapt failed (%s): %s", source, exc)
        record_best_effort_skip(f"hook_acl.{source}", exc)
        try:
            from butler.core.metrics_sink import inc

            inc("hook_acl_degraded", labels={"source": str(source)[:48]})
        except Exception:
            pass
        return HookContextView(
            content=_DEGRADED_FALLBACK,
            metadata={
                "source": source,
                "acl_degraded": True,
                "acl_error": str(exc)[:160],
            },
        )


def adapt_hook_context_lines(
    contexts: list[str],
    *,
    source: str = "hook",
    separator: str = "\n\n",
) -> str:
    """Adapt hook context lines into one ACL-safe string (single entry)."""
    parts: list[str] = []
    for raw in contexts:
        view = to_hook_context_view(raw, source=source)
        if view.content:
            parts.append(view.content)
    return separator.join(parts)


def apply_hook_context_to_diagnostics(
    view: HookContextView,
    diagnostics: dict[str, Any] | None,
) -> None:
    if not isinstance(diagnostics, dict):
        return
    diagnostics["hook_context_view_version"] = view.schema_version
    shape = view.metadata.get("acl_shape")
    if shape:
        diagnostics["hook_acl_shape"] = shape
    if view.metadata.get("acl_warn") or view.metadata.get("acl_degraded"):
        diagnostics["hook_acl_degraded"] = True
