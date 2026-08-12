"""Phase helpers extracted from ``AgentLoop._run_turn_body`` (R1-8 split).

This module re-exports from the new ``butler.core.agent_loop`` package
for backward compatibility.

.. deprecated:: 4.5
    Import from ``butler.core.agent_loop.phases`` instead. This module will
    be removed in a future version.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.core.agent_loop_phases is deprecated. "
    "Import from butler.core.agent_loop.phases instead.",
    DeprecationWarning,
    stacklevel=2,
)

from butler.core.agent_loop.phases import (
    TurnBodyState,
    _audit_session_key,
    _mark_interrupted_status,
    _phase_call_llm,
    _phase_dispatch_tools,
    _phase_finalize,
    _phase_init,
    _phase_maybe_compact_turn,
    _phase_resolve_user_text,
    _phase_enrich_user_text,
    _prepare_skill_tool_context,
    _store_reasoning_on_message,
)

__all__ = [
    "TurnBodyState",
    "_audit_session_key",
    "_mark_interrupted_status",
    "_phase_call_llm",
    "_phase_dispatch_tools",
    "_phase_finalize",
    "_phase_init",
    "_phase_maybe_compact_turn",
    "_phase_resolve_user_text",
    "_phase_enrich_user_text",
    "_prepare_skill_tool_context",
    "_store_reasoning_on_message",
]
