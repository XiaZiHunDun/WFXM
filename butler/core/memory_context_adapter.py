"""Anti-corruption adapter: external memory prefetch shapes → LoopMemoryView."""

from __future__ import annotations

from typing import Any

from butler.contracts.memory_ports import LoopMemoryView


def to_loop_memory_view(
    incoming: Any,
    *,
    source: str = "memory_prefetch",
) -> LoopMemoryView:
    """Convert external memory payload; never raises to callers."""
    from butler.core.memory_context_adapter_ops import to_loop_memory_view_loud

    return to_loop_memory_view_loud(incoming, source=source)


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
