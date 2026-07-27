"""R1-6 in-session pipeline phases for ``ButlerMessageHandler._handle_message_locked``.

Deprecated: Use `butler.gateway.locked_phases` package instead.
"""

from __future__ import annotations

import warnings

warnings.warn(
    "butler.gateway.locked_phases module is deprecated, "
    "use butler.gateway.locked_phases package instead",
    DeprecationWarning,
    stacklevel=2,
)

from butler.gateway.locked_phases.__init__ import (
    LockedTurnState,
    _phase_apply_correction_intent,
    _phase_apply_github_issues_intent,
    _phase_apply_normalizers_and_slash,
    _phase_apply_prompt_hooks,
    _phase_augment_prompt,
    _phase_init_loop_role,
    _phase_validate_loop_messages,
    _phase_resolve_turn_budget,
    _phase_hygiene_compress,
    _phase_prefetch_and_callbacks,
    _phase_execute_turn,
    _phase_finalize_turn,
    _phase_format_turn_response,
    _phase_format_error_card,
)

__all__ = [
    "LockedTurnState",
    "_phase_apply_correction_intent",
    "_phase_apply_github_issues_intent",
    "_phase_apply_normalizers_and_slash",
    "_phase_apply_prompt_hooks",
    "_phase_augment_prompt",
    "_phase_init_loop_role",
    "_phase_validate_loop_messages",
    "_phase_resolve_turn_budget",
    "_phase_hygiene_compress",
    "_phase_prefetch_and_callbacks",
    "_phase_execute_turn",
    "_phase_finalize_turn",
    "_phase_format_turn_response",
    "_phase_format_error_card",
]