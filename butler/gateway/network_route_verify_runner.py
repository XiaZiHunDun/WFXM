"""Gateway-side handler route sim (ENG-7 — tools must not import message_handler)."""

from __future__ import annotations

import time

from butler.tools.network_route_verify import (
    HandlerRouteReport,
    NetworkRouteManifest,
)


def run_handler_route_cases(
    manifest: NetworkRouteManifest,
    *,
    owner_id: str = "owner-route-handler-sim",
    project_name: str = "",
    strict: bool = False,
) -> HandlerRouteReport:
    from butler.gateway.message_handler import ButlerMessageHandler
    from butler.gateway.network_route_verify_runner_ops import run_handler_route_case_safe

    report = HandlerRouteReport(ok=True)
    handler = ButlerMessageHandler(channel="gateway")

    for case in manifest.handler_cases:
        sk = f"wechat:{owner_id}:route-h-{time.time_ns()}"
        outcome = run_handler_route_case_safe(
            handler,
            case,
            owner_id=owner_id,
            session_key=sk,
            project_name=project_name,
            strict=strict,
        )
        report.cases.append(outcome["entry"])
        report.errors.extend(outcome["errors"])
        report.warnings.extend(outcome["warnings"])
        if not outcome["ok"]:
            report.ok = False

    return report


__all__ = ["run_handler_route_cases"]
