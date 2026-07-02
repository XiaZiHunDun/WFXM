"""Dev delegate session bootstrap (extracted from ``delegate_phases`` ENG-2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState


def init_dev_engine_state_for_delegate(state: DelegateRunState) -> None:
    """Initialize DevState + DevEnginePlugin for dev delegates (4g / D3-7)."""
    from butler.dev_engine.delegate_init_ops import init_dev_engine_state_loud

    init_dev_engine_state_loud(state)


__all__ = ["init_dev_engine_state_for_delegate"]
