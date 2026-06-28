"""Gateway-side handler route sim (ENG-7 — tools must not import message_handler)."""

from __future__ import annotations

import time
from typing import Any

from butler.tools.network_route_verify import (
    HandlerRouteCase,
    HandlerRouteReport,
    NetworkRouteManifest,
    evaluate_handler_tool_route,
)


def run_handler_route_cases(
    manifest: NetworkRouteManifest,
    *,
    owner_id: str = "owner-route-handler-sim",
    project_name: str = "",
    strict: bool = False,
) -> HandlerRouteReport:
    from butler.gateway.message_handler import ButlerMessageHandler

    report = HandlerRouteReport(ok=True)
    handler = ButlerMessageHandler(channel="gateway")

    for case in manifest.handler_cases:
        sk = f"wechat:{owner_id}:route-h-{time.time_ns()}"
        entry: dict[str, Any] = {"name": case.name, "session_key": sk}
        try:
            if project_name:
                handler.handle_message(
                    f"/切换 {project_name}",
                    session_key=sk,
                    platform="wechat",
                    external_id=owner_id,
                )
            reply = handler.handle_message(
                case.user_text,
                session_key=sk,
                platform="wechat",
                external_id=owner_id,
            ) or ""
            from butler.gateway.wechat_scenario_sim import load_turn_tools

            tools = load_turn_tools(
                handler,
                owner_id=owner_id,
                session_key=sk,
            )
            entry["tools"] = tools
            entry["reply_preview"] = reply.replace("\n", " ")[:200]
            entry["strict"] = strict
            errors, warnings = evaluate_handler_tool_route(tools, reply, case, strict=strict)
            entry["warnings"] = warnings
            if errors:
                entry["ok"] = False
                report.ok = False
                for err in errors:
                    report.errors.append(f"{case.name}: {err}")
            else:
                entry["ok"] = True
            for warn in warnings:
                report.warnings.append(f"{case.name}: {warn}")
        except Exception as exc:
            entry["ok"] = False
            entry["error"] = str(exc)[:200]
            report.errors.append(f"{case.name}: {exc}")
            report.ok = False
        report.cases.append(entry)

    return report


__all__ = ["run_handler_route_cases"]
