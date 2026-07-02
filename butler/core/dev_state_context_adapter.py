"""Anti-corruption adapter: external dev state shapes → LoopDevStateView."""

from __future__ import annotations

from typing import Any

from butler.contracts.dev_state_ports import LoopDevStateView


def to_loop_dev_state_view(
    incoming: Any,
    *,
    source: str = "unknown",
) -> LoopDevStateView:
    """Convert external dev state payload; never raises."""
    from butler.core.dev_state_context_adapter_ops import to_loop_dev_state_view_loud

    return to_loop_dev_state_view_loud(incoming, source=source)


def loop_dev_state_view_to_payload(view: LoopDevStateView) -> dict[str, Any]:
    """Normalize outbound delegate dev_engine dict."""
    out: dict[str, Any] = {
        "phase": view.phase,
        "iterations": view.iterations,
        "edits": view.edits,
        "fixes": view.fixes,
        "dev_state_view_version": view.schema_version,
    }
    if view.verify_passed is not None:
        out["verify_passed"] = view.verify_passed
    if view.review_passed is not None:
        out["review_passed"] = view.review_passed
    if view.is_terminal:
        out["is_terminal"] = True
    shape = view.metadata.get("acl_shape")
    if shape:
        out["dev_state_acl_shape"] = shape
    return out


def apply_dev_state_view_to_diagnostics(
    view: LoopDevStateView,
    diagnostics: dict[str, Any] | None,
) -> None:
    if not isinstance(diagnostics, dict):
        return
    diagnostics["dev_state_view_version"] = view.schema_version
    diagnostics["dev_state_phase"] = view.phase
    if view.verify_passed is not None:
        diagnostics["dev_state_verify_passed"] = view.verify_passed
    if view.review_passed is not None:
        diagnostics["dev_state_review_passed"] = view.review_passed
    if view.metadata.get("acl_degraded"):
        diagnostics["dev_state_acl_degraded"] = True


def dev_engine_dict_to_view(dev_engine: dict[str, Any] | None, *, source: str = "delegate") -> LoopDevStateView:
    if not isinstance(dev_engine, dict):
        return to_loop_dev_state_view(None, source=source)
    return to_loop_dev_state_view(dev_engine, source=source)
