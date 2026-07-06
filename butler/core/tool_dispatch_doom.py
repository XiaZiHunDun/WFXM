"""Doom-loop ask-mode handler extracted from tool_dispatch (P1-C line budget)."""

from __future__ import annotations

from typing import Any, cast


def handle_doom_loop_ask(
    before: Any,
    name: str,
    args: dict[str, Any],
    *,
    session_key: str,
) -> str | None:
    from butler.core.tool_dispatch_doom_ops import handle_doom_loop_ask_loud

    return cast(
        str | None,
        handle_doom_loop_ask_loud(
            before,
            name,
            args,
            session_key=session_key,
        ),
    )


__all__ = ["handle_doom_loop_ask"]
