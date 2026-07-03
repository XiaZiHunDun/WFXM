"""Handler route case execution fail-closed helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.tools.network_route_verify import HandlerRouteCase, evaluate_handler_tool_route


def run_handler_route_case_safe(
    handler: Any,
    case: HandlerRouteCase,
    *,
    owner_id: str,
    session_key: str,
    project_name: str,
    strict: bool,
) -> dict[str, Any]:
    entry: dict[str, Any] = {"name": case.name, "session_key": session_key}
    try:
        if project_name:
            handler.handle_message(
                f"/切换 {project_name}",
                session_key=session_key,
                platform="wechat",
                external_id=owner_id,
            )
        reply = handler.handle_message(
            case.user_text,
            session_key=session_key,
            platform="wechat",
            external_id=owner_id,
        ) or ""
        from butler.gateway.wechat_scenario_sim import load_turn_tools

        tools = load_turn_tools(
            handler,
            owner_id=owner_id,
            session_key=session_key,
        )
        entry["tools"] = tools
        entry["reply_preview"] = reply.replace("\n", " ")[:200]
        entry["strict"] = strict
        errors, warnings = evaluate_handler_tool_route(tools, reply, case, strict=strict)
        entry["warnings"] = warnings
        if errors:
            entry["ok"] = False
            return {
                "entry": entry,
                "errors": [f"{case.name}: {err}" for err in errors],
                "warnings": [f"{case.name}: {warn}" for warn in warnings],
                "ok": False,
            }
        entry["ok"] = True
        return {
            "entry": entry,
            "errors": [],
            "warnings": [f"{case.name}: {warn}" for warn in warnings],
            "ok": True,
        }
    except Exception as exc:
        entry["ok"] = False
        entry["error"] = str(exc)[:200]
        return {
            "entry": entry,
            "errors": [f"{case.name}: {exc}"],
            "warnings": [],
            "ok": False,
        }
