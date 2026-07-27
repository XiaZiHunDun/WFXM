"""Phase helpers extracted from ``AgentLoop._run_turn_body`` (R1-8 split).

Deprecated: Use `butler.core.agent_loop.phases` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.core.agent_loop.phases module is deprecated, "
    "use butler.core.agent_loop.phases package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.core.agent_loop.phases import (
    TurnBodyState,
    _phase_init,
    _phase_call_llm,
    _phase_dispatch_tools,
    _phase_finalize,
    _phase_maybe_compact_turn,
    _mark_interrupted_status,
    _phase_resolve_user_text,
    _phase_enrich_user_text,
)

__all__ = [
    "TurnBodyState",
    "_phase_init",
    "_phase_call_llm",
    "_phase_dispatch_tools",
    "_phase_finalize",
    "_phase_maybe_compact_turn",
    "_mark_interrupted_status",
    "_phase_resolve_user_text",
    "_phase_enrich_user_text",
]