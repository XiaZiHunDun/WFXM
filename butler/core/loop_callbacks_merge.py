"""Pure merger for :class:`LoopCallbacks` objects.

Historically this lived in ``butler.gateway.outbound_bridge`` and the agent
loop lazy-imported it from gateway on every ``run()`` invocation, which was a
core→gateway layering violation (audit R1-2).

The function has no gateway dependencies — it only manipulates the
``LoopCallbacks`` dataclass defined in ``butler.core.loop_types`` — so it
belongs in core. ``butler.gateway.outbound_bridge`` keeps a re-export for
backward compatibility with existing callers.
"""

from __future__ import annotations

from typing import Any

from butler.core.loop_types import LoopCallbacks


def merge_loop_callbacks(base: Any, extra: Any | None) -> Any:
    """Merge optional per-run callbacks onto a base :class:`LoopCallbacks`.

    Each field from ``extra`` overrides the matching field on ``base`` when set
    (``not None``); otherwise the ``base`` value is preserved. Returns a brand
    new ``LoopCallbacks`` instance and never mutates the inputs.

    Short-circuits:
    - ``extra is None`` → returns ``base`` unchanged.
    - ``base is None`` → returns ``extra`` unchanged.
    """
    if extra is None:
        return base
    if base is None:
        return extra

    def _pick(name: str) -> Any:
        v = getattr(extra, name, None)
        if v is not None:
            return v
        return getattr(base, name, None)

    return LoopCallbacks(
        on_llm_start=_pick("on_llm_start"),
        on_llm_complete=_pick("on_llm_complete"),
        on_stream_delta=_pick("on_stream_delta"),
        on_stream_boundary=_pick("on_stream_boundary"),
        on_tool_start=_pick("on_tool_start"),
        on_tool_complete=_pick("on_tool_complete"),
        on_error=_pick("on_error"),
        on_iteration=_pick("on_iteration"),
        on_fallback=_pick("on_fallback"),
        pre_llm_transform=_pick("pre_llm_transform"),
        should_continue=_pick("should_continue"),
    )


__all__ = ["merge_loop_callbacks"]
