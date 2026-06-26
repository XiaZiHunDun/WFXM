"""WeChat completion pushes for long gateway turns (outbound bridge, not shell hooks)."""

from __future__ import annotations

import logging
import os
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from butler.gateway.outbound_bridge import GatewayOutboundBridge
    from butler.report import AgentReport

from butler.defaults.env_defaults import GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS
from butler.env_parse import int_env

logger = logging.getLogger(__name__)


def _env_bool(name: str, default: bool) -> bool:
    from butler.env_parse import env_truthy

    return env_truthy(name, default=default)


def _env_float(name: str, default: float) -> float:
    from butler.env_parse import float_env

    return float_env(name, default)


def completion_notify_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_COMPLETION_NOTIFY", True)


def min_elapsed_for_push() -> float:
    return max(
        0.0,
        _env_float(
            "BUTLER_GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS",
            GATEWAY_COMPLETION_NOTIFY_MIN_SECONDS,
        ),
    )


def delegate_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_DELEGATE_COMPLETION_NOTIFY", True)


def delegate_progress_notify_enabled() -> bool:
    """Mid-flight WeChat progress for long delegates (also enables task milestones)."""
    return _env_bool("BUTLER_GATEWAY_DELEGATE_PROGRESS_NOTIFY", False)


def turn_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_TURN_COMPLETION_NOTIFY", True)


def workflow_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_WORKFLOW_COMPLETION_NOTIFY", True)


def timeout_completion_enabled() -> bool:
    return _env_bool("BUTLER_GATEWAY_TIMEOUT_COMPLETION_NOTIFY", True)


def delegate_completion_mode() -> str:
    """last: only the final delegate in a turn pushes; each: up to N; once: first only."""
    return (os.getenv("BUTLER_GATEWAY_DELEGATE_COMPLETION_MODE", "last") or "last").strip().lower()


def delegate_completion_max_each() -> int:
    from butler.defaults.env_defaults import GATEWAY_DELEGATE_COMPLETION_MAX_EACH

    return int_env(
        "BUTLER_GATEWAY_DELEGATE_COMPLETION_MAX_EACH",
        GATEWAY_DELEGATE_COMPLETION_MAX_EACH,
        min=1,
    )


def format_outbound_diagnostic_lines(
    session_key: str = "",
    *,
    chat_id: str = "",
) -> list[str]:
    """Lines for ``/诊断`` — completion notify policy + session push stats."""
    from butler.gateway.completion_telemetry import (
        completion_push_stats,
        push_queue_pending_count,
    )
    from butler.runtime.notify import wechat_push_cooldown_seconds

    mode = delegate_completion_mode()
    flags: list[str] = []
    if completion_notify_enabled():
        flags.append("完成提醒:开")
        flags.append(f"委派={mode}")
        if mode == "each":
            flags.append(f"each≤{delegate_completion_max_each()}")
        flags.append(f"最短{int(min_elapsed_for_push())}s")
        flags.append(f"冷却{int(wechat_push_cooldown_seconds())}s")
        if not delegate_completion_enabled():
            flags.append("委派推:关")
        if not turn_completion_enabled():
            flags.append("整轮推:关")
        if not timeout_completion_enabled():
            flags.append("超时推:关")
    else:
        flags.append("完成提醒:关")
    lines = [f"出站策略: {' · '.join(flags)}"]
    stats = completion_push_stats(session_key or chat_id)
    if any(stats.values()):
        lines.append(
            "出站推送本轮: "
            f"成功{stats['sent']} 失败{stats['failed']} 入队{stats['enqueued']}"
        )
    else:
        lines.append("出站推送本轮: 无记录")
    pending = push_queue_pending_count(chat_id=chat_id)
    if pending:
        lines.append(f"推送队列待发: {pending} 条")
    try:
        from butler.gateway.durable_outbox import outbox_counts

        counts = outbox_counts(chat_id=chat_id)
        if any(counts.values()):
            lines.append(
                "出站留痕: "
                f"pending={counts['pending']} sent={counts['sent']} failed={counts['failed']}"
            )
    except Exception as exc:
        logger.debug("format outbound diagnostic lines skipped: %s", exc)
    return lines


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
    mode = delegate_completion_mode()
    if mode == "once" and bridge.delegate_push_count >= 1:
        return False
    if mode == "each" and bridge.delegate_push_count >= delegate_completion_max_each():
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
    if bridge.completion_push_sent or bridge.timeout_notified:
        return False
    if not bridge.ack_sent:
        return False
    return elapsed_turn_seconds >= min_elapsed_for_push()


def should_push_timeout_completion(
    bridge: GatewayOutboundBridge,
    elapsed_turn_seconds: float,
) -> bool:
    if not completion_notify_enabled() or not timeout_completion_enabled():
        return False
    if bridge.timeout_notified or bridge.completion_push_sent:
        return False
    return bridge.ack_sent or elapsed_turn_seconds >= min_elapsed_for_push()


def build_timeout_text(*, timeout_seconds: float, elapsed_seconds: float) -> str:
    limit = int(timeout_seconds)
    return (
        f"⏱ 处理超时（已超过 {limit} 秒，本轮约 {format_elapsed(elapsed_seconds)}）\n"
        "请稍后重试，或发 /诊断 查看状态。"
    )


def try_push_turn_timeout(
    bridge: GatewayOutboundBridge | None,
    *,
    timeout_seconds: float,
    elapsed_seconds: float,
) -> bool:
    br = bridge
    if br is None:
        return False
    if not should_push_timeout_completion(br, elapsed_seconds):
        return False
    return br.schedule_completion_push(
        build_timeout_text(
            timeout_seconds=timeout_seconds,
            elapsed_seconds=elapsed_seconds,
        ),
        kind="timeout",
    )


def flush_pending_delegate_completion(bridge: GatewayOutboundBridge) -> bool:
    """Push deferred delegate report (``delegate_completion_mode=last``)."""
    report = bridge.take_pending_delegate_report()
    if report is None:
        return False
    if (
        getattr(bridge, "_final_sent", False)
        and getattr(bridge, "_main_reply_chars", 0) > 0
    ):
        from butler.gateway.outbound_bridge import suppress_completion_after_main_enabled

        if suppress_completion_after_main_enabled():
            return False
    elapsed = time.monotonic() - bridge.turn_started_at if bridge.turn_started_at else 0.0
    if not should_push_delegate_completion(bridge, elapsed):
        return False
    text = build_delegate_completion_message(
        report,
        prefix="📋 委派阶段完成",
        platform="wechat",
    )
    return bridge.schedule_completion_push(text, kind="delegate")


def _workflow_push_prefix(report: AgentReport) -> str:
    if report.success:
        return "📋 工作流阶段完成"
    return "⚠️ 工作流未完成"


async def deliver_completion_push(
    adapter: Any,
    chat_id: str,
    body: str,
    *,
    kind: str,
) -> bool:
    """Send completion text with shared WeChat cooldown; enqueue on retryable failure."""
    import asyncio

    from butler.runtime.notify import (
        mark_wechat_push_sent,
        should_enqueue_wechat_push_failure,
        wait_wechat_push_cooldown,
    )
    from butler.runtime.push_queue import enqueue_failed_push
    from butler.gateway.durable_outbox import (
        enqueue_outbox_message,
        mark_outbox_failed,
        mark_outbox_sent,
    )

    from butler.gateway.completion_telemetry import (
        record_completion_push_enqueued,
        record_completion_push_failed,
        record_completion_push_sent,
    )

    telemetry_key = chat_id or ""
    from butler.gateway.pii_scrub import scrub_outbound_text

    body = scrub_outbound_text(body)
    outbox_id = enqueue_outbox_message(chat_id, body, kind=kind)
    await asyncio.to_thread(wait_wechat_push_cooldown)
    title = f"[Butler] {kind}完成提醒"
    try:
        result = await adapter.send(chat_id, body)
        err = getattr(result, "error", None)
        success = getattr(result, "success", True)
        if success is False or err:
            raise RuntimeError(str(err or "send failed"))
        await asyncio.to_thread(mark_wechat_push_sent)
        mark_outbox_sent(outbox_id)
        record_completion_push_sent(session_key=telemetry_key)
        return True
    except Exception as exc:
        logger.warning("Gateway completion push failed kind=%s: %s", kind, exc)
        mark_outbox_failed(outbox_id, error=str(exc))
        if should_enqueue_wechat_push_failure(str(exc)):
            enqueue_failed_push(title, body, chat_id=chat_id)
            record_completion_push_enqueued(session_key=telemetry_key)
        else:
            record_completion_push_failed(session_key=telemetry_key)
        return False


def try_push_workflow_failure(
    bridge: GatewayOutboundBridge | None,
    workflow_name: str,
    error: Exception | str,
    *,
    session_key: str = "",
) -> bool:
    from butler.report import AgentReport, cache_report, get_last_report

    br = bridge
    if br is None:
        return False
    report = get_last_report(session_key)
    if report is None:
        msg = str(error)[:2000]
        report = AgentReport(
            headline=f"工作流 {workflow_name} 失败",
            summary=msg,
            success=False,
            task_preview=f"workflow:{workflow_name}"[:200],
            issues=[msg[:500]],
        )
        cache_report(report, session_key=session_key or "default")
    elapsed = time.monotonic() - br.turn_started_at if br.turn_started_at else 0.0
    if not should_push_workflow_completion(br, elapsed):
        return False
    text = build_report_push_text(report, prefix=_workflow_push_prefix(report))
    return br.schedule_completion_push(text, kind="workflow")


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
        if delegate_completion_mode() == "last":
            br.set_pending_delegate_report(report)
            return True
        if not should_push_delegate_completion(br, elapsed):
            return False
        prefix = "📋 委派阶段完成"
    elif kind == "workflow":
        if not should_push_workflow_completion(br, elapsed):
            return False
        prefix = _workflow_push_prefix(report)
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
