"""CLI: ``butler events ...`` — 事件指标与审计日志查询."""

from __future__ import annotations

import argparse
import json
from typing import Any, cast


def register_events_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    """Register the events subcommand parser."""
    events = sub.add_parser(
        "events",
        help="事件系统：实时指标与审计日志查询",
        description="查询事件消费者收集的实时指标、审计日志和会话活动",
    )
    events_sub = events.add_subparsers(dest="events_cmd", required=True)

    # Metrics subcommand
    metrics_p = events_sub.add_parser(
        "metrics",
        help="查看实时事件指标",
        description="显示事件消费者收集的实时指标，包括事件计数、LLM 调用、工具调用等",
    )
    metrics_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    metrics_p.set_defaults(func=_cmd_events_metrics)

    # Audit subcommand
    audit_p = events_sub.add_parser(
        "audit",
        help="查看审计日志",
        description="查询事件审计日志，支持按会话和事件类型过滤",
    )
    audit_p.add_argument("--session", type=str, default="", help="按会话 ID 过滤")
    audit_p.add_argument("--type", type=str, default="", help="按事件类型过滤")
    audit_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    audit_p.add_argument("--limit", type=int, default=50, help="返回条数限制")
    audit_p.set_defaults(func=_cmd_events_audit)

    # Sessions subcommand
    sessions_p = events_sub.add_parser(
        "sessions",
        help="查看活跃会话",
        description="显示当前活跃会话及其活动统计",
    )
    sessions_p.add_argument("--json", action="store_true", help="以 JSON 格式输出")
    sessions_p.add_argument("--minutes", type=int, default=60, help="活跃时间阈值（分钟）")
    sessions_p.set_defaults(func=_cmd_events_sessions)

    # Reset subcommand
    reset_p = events_sub.add_parser(
        "reset",
        help="重置事件指标",
        description="重置所有事件消费者的指标数据",
    )
    reset_p.set_defaults(func=_cmd_events_reset)


def _cmd_events_metrics(ns: argparse.Namespace) -> int:
    """Display event metrics."""
    from butler.core.events.event_consumer import get_event_metrics_collector

    collector = get_event_metrics_collector()
    metrics = collector.get_metrics()

    if ns.json:
        print(json.dumps(metrics, indent=2, ensure_ascii=False))
        return 0

    print("=" * 60)
    print("事件系统实时指标")
    print("=" * 60)
    print(f"运行时间: {metrics['uptime_seconds']:.2f} 秒")
    print(f"总事件数: {metrics['total_events']}")
    print(f"总会话数: {metrics['total_sessions']}")
    print(f"LLM API 调用: {metrics['llm_api_call_count']}")
    print(f"工具调用: {metrics['tool_call_count']}")
    print(f"记忆同步: {metrics['memory_sync_count']}")
    print(f"错误数: {metrics['error_count']}")
    print()
    print("事件类型分布:")
    for event_type, count in sorted(metrics["event_counts"].items(), key=lambda x: x[1], reverse=True):
        print(f"  {event_type}: {count}")
    print()
    print("会话分布:")
    for session_key, count in sorted(metrics["session_counts"].items(), key=lambda x: x[1], reverse=True)[:5]:
        print(f"  {session_key}: {count} 次事件")

    return 0


def _cmd_events_audit(ns: argparse.Namespace) -> int:
    """Display audit log."""
    from butler.core.events.event_consumer import get_event_audit_logger

    logger = get_event_audit_logger()

    if ns.session:
        history = logger.search_by_session(ns.session)
    elif ns.type:
        history = logger.search_by_type(ns.type)
    else:
        history = logger.get_history()

    # Apply limit
    history = history[:ns.limit]

    if ns.json:
        print(json.dumps(history, indent=2, ensure_ascii=False, default=str))
        return 0

    print("=" * 60)
    print("事件审计日志")
    print("=" * 60)
    print(f"共 {len(history)} 条记录")
    print()

    for entry in history:
        print(f"事件 ID: {entry['event_id']}")
        print(f"事件类型: {entry['event_type']}")
        print(f"会话: {entry['session_key'] or '(无)'}")
        print(f"时间: {entry['timestamp']}")
        print(f"数据: {json.dumps(entry['data'], ensure_ascii=False)[:200]}")
        print("-" * 40)

    return 0


def _cmd_events_sessions(ns: argparse.Namespace) -> int:
    """Display active sessions."""
    from butler.core.events.event_consumer import get_session_activity_tracker

    tracker = get_session_activity_tracker()
    active = tracker.get_active_sessions(minutes=ns.minutes)

    if ns.json:
        print(json.dumps(active, indent=2, ensure_ascii=False, default=str))
        return 0

    print("=" * 60)
    print("活跃会话")
    print("=" * 60)
    print(f"过去 {ns.minutes} 分钟内活跃的会话: {len(active)}")
    print()

    for session_key, activity in active.items():
        print(f"会话: {session_key}")
        print(f"  事件数: {activity['event_count']}")
        print(f"  LLM 调用: {activity['llm_calls']}")
        print(f"  工具调用: {activity['tool_calls']}")
        print(f"  错误数: {activity['errors']}")
        print(f"  最后活动: {activity['last_activity']}")
        print()

    return 0


def _cmd_events_reset(ns: argparse.Namespace) -> int:
    """Reset event metrics."""
    from butler.core.events.event_consumer import (
        get_event_metrics_collector,
        get_event_audit_logger,
        get_session_activity_tracker,
    )

    get_event_metrics_collector().reset()
    get_event_audit_logger().reset()
    get_session_activity_tracker().reset()

    print("事件指标已重置")
    return 0