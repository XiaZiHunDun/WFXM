"""B9 / drill workspace seeding for dev delegates (ENG-2)."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from butler.tools.delegate_phases import DelegateRunState


def prepare_b9_benchmark_workspace(state: DelegateRunState) -> None:
    """Seed B9 workspace read_state and inject file preamble into delegate context."""
    from butler.dev_engine.b9_delegate_gate import (
        SWE_LIVE_CATEGORY,
        is_benchmark_category,
        prepare_b9_subagent_workspace,
    )
    from butler.tools.delegate_impl import (
        _inject_project_agent_skills,
        _project_agent_raw_message,
    )

    if not is_benchmark_category(state.category, state.category_meta):
        return
    ws = _project_workspace_path(state)
    if ws is None:
        return
    sk = state.child_session_key or state.session_key or "_default"
    cat = str(state.category_meta.get("category") or state.category or "")
    depth = 2 if cat == SWE_LIVE_CATEGORY else 1
    preamble = prepare_b9_subagent_workspace(ws, session_key=sk, max_depth=depth)
    if not preamble:
        return
    state.context = f"{preamble}\n\n{state.context}".strip()
    state.raw_user_msg = _project_agent_raw_message(task=state.task, context=state.context)
    state.user_msg = _inject_project_agent_skills(state.orch, state.raw_user_msg)


def prepare_isolated_workspace_read_state(state: DelegateRunState) -> None:
    """Seed read_state for drill / head-to-head isolated workspaces."""
    cat = str(state.category_meta.get("category") or state.category or "").strip().lower()
    if not (cat.startswith("head-to-head") or cat.endswith("-drill") or "drill" in cat):
        return
    ws = _project_workspace_path(state)
    if ws is None:
        return
    sk = state.child_session_key or state.session_key or "_default"
    from butler.dev_engine.delegate_workspace_ops import seed_isolated_workspace_read_state_safe

    seed_isolated_workspace_read_state_safe(ws, session_key=sk)


def _project_workspace_path(state: DelegateRunState) -> Path | None:
    if state.project is None or not getattr(state.project, "workspace", None):
        return None
    try:
        ws = Path(state.project.workspace)
    except (TypeError, ValueError, OSError):
        return None
    if not ws.is_dir():
        return None
    return ws


__all__ = [
    "prepare_b9_benchmark_workspace",
    "prepare_isolated_workspace_read_state",
]
