"""Butler Agent Loop — the core LLM conversation engine.

This module re-exports from the new ``butler.core.agent_loop`` package
for backward compatibility.

.. deprecated:: 4.5
    Import from ``butler.core.agent_loop`` package instead. This module will
    be removed in a future version.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.core.agent_loop is deprecated. "
    "Import from butler.core.agent_loop package instead.",
    DeprecationWarning,
    stacklevel=2,
)

from butler.core.agent_loop.loop import AgentLoop
from butler.core.agent_loop.phases import (
    TurnBodyState,
    _mark_interrupted_status,
    _phase_call_llm,
    _phase_dispatch_tools,
    _phase_finalize,
    _phase_init,
    _phase_resolve_user_text,
    _phase_enrich_user_text,
)
from butler.core.loop_types import LoopCallbacks, LoopResult

__all__ = [
    "AgentLoop",
    "LoopCallbacks",
    "LoopResult",
    "TurnBodyState",
    "_mark_interrupted_status",
    "_phase_call_llm",
    "_phase_dispatch_tools",
    "_phase_finalize",
    "_phase_init",
    "_phase_resolve_user_text",
    "_phase_enrich_user_text",
]
