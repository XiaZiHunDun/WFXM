from __future__ import annotations

from typing import TYPE_CHECKING, Optional, cast

from butler.core.best_effort import safe_best_effort
from butler.core.correction_intent import try_handle_correction_intent
from butler.mcp.github_grounding import try_handle_github_issues_intent

from .state import LockedTurnState, _load_normalizers

if TYPE_CHECKING:
    from butler.gateway.message_handler import ButlerMessageHandler


def _phase_apply_correction_intent(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    def _run() -> Optional[str]:
        return cast(
            Optional[str],
            try_handle_correction_intent(
                handler._orchestrator,
                state.text,
                session_key=state.session_key,
            ),
        )

    return cast(
        Optional[str],
        safe_best_effort(_run, label="locked_phases.correction_intent"),
    )


def _phase_apply_github_issues_intent(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    del handler

    def _run() -> Optional[str]:
        return cast(Optional[str], try_handle_github_issues_intent(state.text))

    return cast(
        Optional[str],
        safe_best_effort(_run, label="locked_phases.github_issues_intent"),
    )


def _phase_apply_normalizers_and_slash(
    handler: "ButlerMessageHandler",
    state: LockedTurnState,
) -> Optional[str]:
    for normalizer in _load_normalizers():
        cmd = normalizer(state.text)
        if cmd is not None:
            response = handler._handle_command(
                cmd,
                session_key=state.session_key,
                platform=state.platform,
                external_id=state.external_id,
            )
            if response is not None:
                return cast(str, response)
    if state.text.startswith("/"):
        response = handler._handle_command(
            state.text,
            session_key=state.session_key,
            platform=state.platform,
            external_id=state.external_id,
        )
        if response is not None:
            return cast(str, response)
    return None