"""Anti-corruption adapter: external hook shapes → HookContextView."""

from __future__ import annotations

from typing import Any

from butler.contracts.hook_context_ports import HookContextView


def to_hook_context_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> HookContextView:
    """Convert external hook payload; never raises to callers."""
    from butler.core.hook_context_adapter_ops import to_hook_context_view_loud

    return to_hook_context_view_loud(incoming, source=source)


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
