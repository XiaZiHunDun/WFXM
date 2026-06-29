"""Slash command dispatch + health formatting for ButlerMessageHandler (ENG-3)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from butler.core.agent_loop import LoopResult
    from butler.gateway.message_handler import ButlerMessageHandler


def handle_slash_command(
    handler: ButlerMessageHandler,
    text: str,
    *,
    session_key: str = "default",
    platform: str = "unknown",
    external_id: str | None = None,
) -> Optional[str]:
    """Handle Butler slash commands. Returns response or None.

    owner-gate-opt-out: 纯 dispatch 路由；各子命令 handler 在 command_registry 内
    自行调用 require_owner / is_gateway_owner，本函数不重复 gate。
    """
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    import butler.gateway.commands  # noqa: F401 — ensure handlers registered
    from butler.gateway.command_registry import CommandContext, dispatch

    ctx = CommandContext(
        cmd=cmd,
        arg=arg,
        session_key=session_key,
        platform=platform,
        external_id=external_id,
        orchestrator=handler._orchestrator,
        session_registry=handler._session_registry,
    )
    handled, result = dispatch(ctx)
    if handled:
        return result
    return None


def format_health_summary(handler: ButlerMessageHandler, session_key: str = "default") -> str:
    from butler.gateway.handler_helpers import _tool_audit_summary
    from butler.ops.health_report import (
        HealthReportInput,
        build_health_report,
        collect_mem_stats_for_health,
    )

    health = handler.last_health_summary(session_key)
    return build_health_report(
        HealthReportInput(
            session_key=session_key,
            health=health,
            tool_summary=_tool_audit_summary(session_key),
            mem_stats=collect_mem_stats_for_health(
                handler._orchestrator, session_key, health
            ),
            orchestrator=handler._orchestrator,
        )
    )


def format_loop_response(result: LoopResult, platform: str) -> str:
    """Format the response appropriately for the platform."""
    if platform in ("wechat", "weixin"):
        from butler.report.format import wechat_response_text

        return wechat_response_text(result)

    if not result.final_response:
        return "（执行完成，无文字输出）"
    return result.final_response


__all__ = ["format_health_summary", "format_loop_response", "handle_slash_command"]
