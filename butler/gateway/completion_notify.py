"""WeChat completion pushes for long gateway turns (outbound bridge, not shell hooks)."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.gateway.outbound_bridge import GatewayOutboundBridge
    from butler.report import AgentReport

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    from butler.env_parse import env_truthy

    return env_truthy(name, default=default)


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, "").strip() or default)
    except ValueError:
        return default


def completion_notify_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_COMPLETION_NOTIFY", True)


def min_elapsed_for_push() -> float:
    return max(0.0, _env_float("BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS", 90.0))


def delegate_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_DELEGATE_COMPLETION_NOTIFY", True)


def turn_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_TURN_COMPLETION_NOTIFY", True)


def workflow_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_WORKFLOW_COMPLETION_NOTIFY", True)


def format_elapsed(seconds: float) -> str:
    total = max(0, int(seconds))
    if total < 60:
        return f"{total} 秒"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} 分 {secs} 秒" if secs else f"{minutes} 分钟"
    hours, rem = divmod(minutes, 60)
    return f"{hours} 小时 {rem} 分钟"


def build_report_push_text(report: AgentReport, *, prefix: str = "") -> str:
    from butler.report import format_for_wechat

    body = format_for_wechat(report)
    if prefix:
        return f"{prefix}\n\n{body}".strip()
    return body


def build_turn_complete_text(*, elapsed_seconds: float) -> str:
    return (
        f"✅ 本轮处理已完成（用时约 {format_elapsed(elapsed_seconds)}）\n"
        "完整回复见上一条；发 /详细 可看报告。"
    )


def should_push_delegate_completion(
    bridge: GatewayOutboundBridge,
    elapsed_turn_seconds: float,
) -> bool:
    if not completion_notify_enabled() or not delegate_completion_enabled():
        return False
    if bridge.completion_push_sent:
        return False
    if bridge.ack_sent:
        return True
    if elapsed_turn_seconds >= min_elapsed_for_push():
        return True
    return _env_bool("BUTLER_GATEWAY_DELEGATE_PUSH_ALWAYS", False)


def should_push_workflow_completion(
    bridge: GatewayOutboundBridge,
    elapsed_turn_seconds: float,
) -> bool:
    if not completion_notify_enabled() or not workflow_completion_enabled():
        return False
    if bridge.completion_push_sent:
        return False
    if bridge.ack_sent:
        return True
    return elapsed_turn_seconds >= min_elapsed_for_push()


def should_push_turn_completion(
    bridge: GatewayOutboundBridge,
    elapsed_turn_seconds: float,
) -> bool:
    if not completion_notify_enabled() or not turn_completion_enabled():
        return False
    if bridge.completion_push_sent:
        return False
    if not bridge.ack_sent:
        return False
    return elapsed_turn_seconds >= min_elapsed_for_push()


def try_push_agent_report(
    report: AgentReport,
    *,
    kind: str,
    bridge: GatewayOutboundBridge | None = None,
    elapsed_turn_seconds: float | None = None,
) -> bool:
    """Schedule a WeChat completion message via the outbound bridge."""
    from butler.gateway.outbound_bridge import get_gateway_bridge_optional

    br = bridge or get_gateway_bridge_optional()
    if br is None:
        return False
    elapsed = (
        float(elapsed_turn_seconds)
        if elapsed_turn_seconds is not None
        else (time.monotonic() - br.turn_started_at if br.turn_started_at else 0.0)
    )
    if kind == "delegate":
        if not should_push_delegate_completion(br, elapsed):
            return False
        prefix = "📋 委派阶段完成"
    elif kind == "workflow":
        if not should_push_workflow_completion(br, elapsed):
            return False
        prefix = "📋 工作流阶段完成"
    else:
        return False
    text = build_report_push_text(report, prefix=prefix)
    return br.schedule_completion_push(text, kind=kind)


def try_push_turn_complete(
    bridge: GatewayOutboundBridge | None,
    *,
    elapsed_seconds: float,
) -> bool:
    from butler.gateway.outbound_bridge import get_gateway_bridge_optional

    br = bridge or get_gateway_bridge_optional()
    if br is None:
        return False
    if not should_push_turn_completion(br, elapsed_seconds):
        return False
    return br.schedule_completion_push(
        build_turn_complete_text(elapsed_seconds=elapsed_seconds),
        kind="turn",
    )
