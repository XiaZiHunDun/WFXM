from __future__ import annotations

from typing import Optional, cast

from butler.hooks.runner import run_user_prompt_submit_hooks

from .state import LockedTurnState


def _phase_apply_prompt_hooks(state: LockedTurnState) -> Optional[str]:
    state.prompt_hooks = run_user_prompt_submit_hooks(
        state.text.strip(),
        session_key=state.session_key,
        platform=state.platform,
    )
    if state.prompt_hooks.blocked:
        return cast(str, state.prompt_hooks.block_message)
    if state.prompt_hooks.prevent_continuation:
        return state.prompt_hooks.stop_message or "已停止（UserPromptSubmit hook）"
    return None