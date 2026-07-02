"""Reflexion ephemeral persist helpers (P0-A)."""

from __future__ import annotations

from butler.core.best_effort import safe_best_effort


def persist_reflexion_episode_safe(
    *,
    tool_name: str,
    failure_count: int,
    last_error: str,
    session_key: str,
) -> None:
    def _run() -> None:
        from butler.core.reflection_closure import persist_reflect_episode
        from butler.core.reflexion_write import write_reflexion_experience

        write_reflexion_experience(
            tool_name=tool_name,
            failure_count=failure_count,
            last_error=last_error,
            session_key=session_key,
        )
        persist_reflect_episode(
            trigger="tool_fail",
            cause=str(last_error or ""),
            strategy="change_tool_or_ask_user",
            detail=f"failures={failure_count}",
            session_key=session_key,
            source="reflexion_ephemeral",
            tool_name=tool_name,
            failure_count=failure_count,
        )

    safe_best_effort(_run, label="reflexion_ephemeral.persist", default=None)
