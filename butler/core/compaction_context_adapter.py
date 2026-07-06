"""Anti-corruption adapter: external compaction shapes → LoopCompactionView."""

from __future__ import annotations

from typing import Any

from butler.contracts.compaction_ports import LoopCompactionView


def to_loop_compaction_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> LoopCompactionView:
    """Convert external compaction payload; never raises to callers."""
    from butler.core.compaction_context_adapter_ops import to_loop_compaction_view_loud

    return to_loop_compaction_view_loud(incoming, source=source)


def apply_compaction_view_to_diagnostics(
    view: LoopCompactionView,
    diagnostics: dict[str, Any] | None,
) -> None:
    """Record ACL observability fields on turn diagnostics."""
    if not isinstance(diagnostics, dict):
        return
    diagnostics["compaction_view_version"] = view.schema_version
    shape = view.metadata.get("acl_shape")
    if shape:
        diagnostics["compaction_acl_shape"] = shape
    if view.metadata.get("acl_warn") or view.metadata.get("acl_degraded"):
        diagnostics["compaction_acl_degraded"] = True


def adapt_hook_contexts(contexts: list[str], *, source: str = "post_compact_hook") -> str:
    """Adapt PostCompact hook context lines into one ACL-safe string."""
    from butler.core.hook_context_adapter import adapt_hook_context_lines

    return str(adapt_hook_context_lines(contexts, source=source, separator="\n"))
