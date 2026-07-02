"""Doom-loop ask-mode handler extracted from tool_dispatch (P1-C line budget)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.tool_guardrails import GuardrailDecision, synthetic_result


def handle_doom_loop_ask(
    before: Any,
    name: str,
    args: dict,
    *,
    session_key: str,
) -> str | None:
    from butler.core.tool_batch import finalize_fallback_tool_result

    try:
        from butler.permissions.doom_loop import check_doom_loop_ask

        block_msg = check_doom_loop_ask(before, name, args)
        if block_msg:

            def _record_reflect() -> None:
                from butler.core.reasoning_trace import record_doom_loop_reflect

                record_doom_loop_reflect(session_key, block_msg, tool_name=name)

            safe_best_effort(_record_reflect, label="tool_dispatch.doom_reflect")
            ask_dec = GuardrailDecision(
                action="block",
                code="doom_loop",
                message=block_msg,
                tool_name=name,
            )
            return finalize_fallback_tool_result(name, args, synthetic_result(ask_dec))
    except Exception:
        return finalize_fallback_tool_result(name, args, synthetic_result(before))
    return None


__all__ = ["handle_doom_loop_ask"]
