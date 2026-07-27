from __future__ import annotations

from typing import Any, Sequence


def _norm_tool_name(name: str) -> str:
    return str(name or "").replace("-", "_")


def _tool_in_list(needle: str, tools: Sequence[str]) -> bool:
    want = _norm_tool_name(needle)
    return any(_norm_tool_name(t) == want for t in tools)


def _any_tool_in_list(needles: Sequence[str], tools: Sequence[str]) -> bool:
    return any(_tool_in_list(n, tools) for n in needles)


def resolve_handler_session_key(
    handler: Any,
    *,
    owner_id: str,
    session_key: str,
    platform: str = "wechat",
) -> str:
    return str(
        handler.resolve_session_key(
            platform=platform,
            external_id=owner_id,
            session_key=session_key,
        )
    )


def _audit_event_count(
    handler: Any,
    *,
    owner_id: str,
    session_key: str,
    platform: str = "wechat",
) -> int:
    # Lazy imports to break circular dependency:
    # butler.tools.registry → butler.core → butler.core.agent_loop
    # → butler.ops → butler.tools.registry
    from butler.tools.registry import get_tool_audit_events

    canonical = resolve_handler_session_key(
        handler,
        owner_id=owner_id,
        session_key=session_key,
        platform=platform,
    )
    return len(get_tool_audit_events(session_key=canonical))


def load_turn_tools(
    handler: Any,
    *,
    owner_id: str,
    session_key: str,
    platform: str = "wechat",
    audit_before: int | None = None,
) -> list[str]:
    # Lazy imports to break circular dependency:
    # butler.tools.registry → butler.core → butler.core.agent_loop
    # → butler.ops → butler.tools.registry
    from butler.tools.registry import get_tool_audit_events
    from butler.core.session_epoch import load_current_turn_tool_actions

    canonical = resolve_handler_session_key(
        handler,
        owner_id=owner_id,
        session_key=session_key,
        platform=platform,
    )
    if audit_before is not None:
        events = get_tool_audit_events(session_key=canonical)[audit_before:]
        audit_tools = [
            str(event.get("tool") or "").strip()
            for event in events
            if str(event.get("tool") or "").strip()
        ]
        if audit_tools:
            return audit_tools
    return [
        str(row.get("tool") or "").strip()
        for row in load_current_turn_tool_actions(canonical)
        if str(row.get("tool") or "").strip()
    ]