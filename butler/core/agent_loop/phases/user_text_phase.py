from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from butler.core.best_effort import safe_best_effort
from butler.core.message_sanitize import sanitize_surrogates
from butler.core.skill_tool_bridge import collect_pinned_tools
from butler.core.session_transcript import record_user_message
from butler.core.system_reminder import maybe_prepend_system_reminder
from butler.core.tool_selector import select_tools_for_context
from butler.core.harness_flags import mcp_deferred_same_turn_enabled, mcp_deferred_tools_enabled
from butler.mcp.deferred import merge_deferred_mcp_into_turn_tools, promote_experience_mcp_tools
from butler.ops.runtime_metrics import inc

from .state import TurnBodyState

if TYPE_CHECKING:
    from butler.core.agent_loop.loop import AgentLoop


def _phase_resolve_user_text(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> None:
    """Phase U1: inject system prompt (first turn), sanitize, prepend system reminder."""
    user_message = state.user_content
    if not loop._messages:
        if loop.system_prompt:
            loop._messages.append(
                {"role": "system", "content": loop.system_prompt}
            )

    user_content = sanitize_surrogates(user_message)

    def _prepend_reminder() -> str:
        return cast(str, maybe_prepend_system_reminder(user_content))

    reminded = safe_best_effort(
        _prepend_reminder,
        label="agent_loop.system_reminder",
        default=user_content,
    )
    if reminded is not None:
        user_content = cast(str, reminded)
    loop._messages.append({"role": "user", "content": user_content})
    state.user_content = user_content


def _prepare_skill_tool_context(
    loop: "AgentLoop",
    user_content: str,
    steer_session: str,
    turn_tools: list[Any],
) -> tuple[set[str], list[Any]]:
    def _run() -> tuple[set[str], list[Any]]:
        skill_pt: set[str] = set()
        skill_pt, exp_mcp = collect_pinned_tools(user_content)
        if exp_mcp:

            def _promote_mcp() -> None:
                nonlocal turn_tools
                if not mcp_deferred_tools_enabled():
                    return
                added, rejected = promote_experience_mcp_tools(
                    exp_mcp,
                    session_key=steer_session,
                )
                if added:
                    loop.diagnostics["experience_mcp_promoted"] = len(added)

                    def _metric() -> None:
                        inc(
                            "execution_pointer_pin",
                            value=len(added),
                            labels={"source": "experience_mcp"},
                            session_key=steer_session,
                        )

                    safe_best_effort(_metric, label="agent_loop.mcp_pin_metric")
                if rejected:
                    loop.diagnostics["experience_mcp_rejected"] = rejected
                if added and mcp_deferred_same_turn_enabled():
                    turn_tools = merge_deferred_mcp_into_turn_tools(
                        turn_tools,
                        session_key=steer_session,
                    )
                    loop.diagnostics["experience_mcp_same_turn"] = len(added)

            safe_best_effort(_promote_mcp, label="agent_loop.mcp_promote")
        if skill_pt:
            loop.diagnostics["experience_pinned_tools"] = len(skill_pt)
        return skill_pt, turn_tools

    result = safe_best_effort(
        _run,
        label="agent_loop.skill_tool_context",
        default=None,
    )
    if result is not None:
        return cast(tuple[set[str], list[Any]], result)
    return set(), turn_tools


def _phase_enrich_user_text(
    loop: "AgentLoop",
    state: TurnBodyState,
) -> None:
    """Phase U2: tool selection (per-turn) + record user message transcript."""
    user_content = state.user_content
    steer_session = state.steer_session
    turn_tools = list(loop.tools or [])

    def _select_tools() -> list[dict[str, Any]]:
        skill_pt, tools = _prepare_skill_tool_context(
            loop, user_content, steer_session, turn_tools,
        )

        def _add_experience_recommendations() -> set[str]:
            try:
                from butler.tools.tool_service import recommend_tools

                recommended = recommend_tools(user_content, top_k=10)
                recommended_names = {
                    rec["tool_name"] for rec in recommended if rec["score"] > 0.3
                }
                if recommended_names:
                    loop.diagnostics["experience_recommended_tools"] = len(recommended_names)
                return recommended_names
            except Exception as e:
                loop._record_skipped_plugin("tool_service_recommend", e)
                return set()

        exp_recommended = safe_best_effort(
            _add_experience_recommendations,
            label="agent_loop.experience_tool_recommend",
            default=set(),
        )

        combined_preferred = (skill_pt or set()) | exp_recommended

        selected, sel_diag = select_tools_for_context(
            tools,
            user_hint=user_content,
            skill_preferred_tools=combined_preferred or None,
        )
        for key, val in sel_diag.items():
            loop.diagnostics[key] = val
        return list(selected)

    selected = safe_best_effort(
        _select_tools,
        label="agent_loop.tool_selector",
        default=None,
    )
    if selected is not None:
        turn_tools = selected

    def _record_user() -> None:
        record_user_message(steer_session, user_content)

    safe_best_effort(_record_user, label="agent_loop.transcript_user")

    state.turn_tools = turn_tools
    loop._turn_tools = turn_tools
