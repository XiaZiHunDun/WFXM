"""Turn-scoped diagnostic lines for ``/health`` and ``/诊断`` (P2-F)."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from butler.core.best_effort import safe_best_effort

if TYPE_CHECKING:
    from butler.ops.health_report import HealthReportInput


def recovery_bucket_lines(health: dict[str, Any], session_key: str) -> list[str]:
    from butler.ops.retry_buckets import format_recovery_bucket_lines

    return format_recovery_bucket_lines(
        session_key=health.get("session_key") or session_key,
    )


def delegate_stale_lines(health: dict[str, Any], session_key: str) -> list[str]:
    from butler.runtime.task_store import (
        count_running_tasks,
        list_recent_tasks,
        mark_stale_tasks,
    )

    lines: list[str] = []
    sk = health.get("session_key") or session_key
    stale = mark_stale_tasks(sk, auto_fail=False)
    running = count_running_tasks(sk)
    if running:
        lines.append(f"委派 running: {running}")
    if stale:
        lines.append(f"委派 stale: {len(stale)}（>阈值未结束）")
        for row in stale[:3]:
            lines.append(
                f"  ⏱ {row.get('task_id')} {(row.get('task_preview') or '')[:40]}"
            )
    for row in list_recent_tasks(sk, limit=2):
        status = str(row.get("status") or "?")
        role = str(row.get("role") or "?")
        preview = str(row.get("task_preview") or "")[:50]
        lines.append(f"最近委派: {role} · {status} · {preview}")
    return lines


def runtime_metrics_line() -> str:
    from butler.ops.runtime_metrics import get_runtime_metrics

    metrics = get_runtime_metrics()
    compaction_count = metrics.get("compaction_count", 0)
    token_estimate = metrics.get("context_token_estimate", "-")
    return f"Context Pipeline: compaction={compaction_count}, tokens≈{token_estimate}"


def stream_probe_turn_lines(orchestrator: Any) -> list[str]:
    from butler.transport.stream_probe import (
        format_stream_probe_lines,
        run_stream_probe,
        stream_probe_enabled,
    )

    if not stream_probe_enabled():
        return []
    run_stream_probe(orchestrator)
    return format_stream_probe_lines()


def schema_optimize_line(health: dict[str, Any], loop_health: dict[str, Any]) -> str:
    from butler.core.schema_optimizer import schema_optimize_enabled

    if not schema_optimize_enabled():
        return ""
    stripped = health.get("schema_optimize_stripped") or loop_health.get(
        "schema_optimize_stripped"
    )
    if not stripped:
        return ""
    return f"Schema 预优化剥离: {int(stripped)}"


def turn_diagnostic_lines(
    inp: "HealthReportInput",
    *,
    hook_lines_fn: Callable[[str, dict[str, Any] | None], list[str]],
) -> list[str]:
    health = inp.health or {}
    loop_health = health.get("loop") if isinstance(health.get("loop"), dict) else {}
    memory_sync = (
        health.get("memory_sync") if isinstance(health.get("memory_sync"), dict) else {}
    )

    schema_recovered = bool(
        health.get("schema_recovered") or loop_health.get("schema_recovered")
    )
    schema_keywords = (
        health.get("schema_keywords_stripped")
        or loop_health.get("schema_keywords_stripped")
        or 0
    )
    skill_matches = health.get("skill_matches") or []
    if not isinstance(skill_matches, list):
        skill_matches = [str(skill_matches)]

    from butler.transport.auxiliary_client import resolve_auxiliary_config

    aux_label = safe_best_effort(
        lambda: (
            f"{resolve_auxiliary_config('post_session').provider or '?'}/"
            f"{resolve_auxiliary_config('post_session').model or '?'}"
        ),
        label="health_report.auxiliary_config",
        default="未配置",
    ) or "未配置"

    from butler.project.lead import is_lead_project, lead_mode_banner_line

    agent_role = str(health.get("gateway_agent_role") or "butler")
    if agent_role == "lead":
        engine_line = lead_mode_banner_line()
    elif agent_role == "plan":
        engine_line = "对话引擎: 规划 Plan"
    else:
        engine_line = "对话引擎: 管家 Butler"
    lead_flag_line = safe_best_effort(
        lambda: (
            f" · 项目 Lead: {'是' if is_lead_project(str(proj.name or ''), project=proj) else '否'}"
            if (proj := inp.orchestrator.project_manager.get_current(session_key=inp.session_key))
            is not None
            else ""
        ),
        label="health_report.lead_flag",
        default="",
    ) or ""
    engine_line += lead_flag_line
    from butler.core.context_budget import format_context_budget_line
    from butler.context_settings import format_context_config_source_line

    context_line = format_context_budget_line(health)
    context_config_line = format_context_config_source_line()
    from butler.core.compaction_status import format_compaction_status_line, format_fact_survival_line
    from butler.core.pipeline_steps import format_pipeline_step_lines
    from butler.tools.path_safety import format_tool_workspace_line

    workspace_line = safe_best_effort(
        lambda: format_tool_workspace_line(
            str(health.get("session_key") or inp.session_key or "")
        ),
        label="health_report.tool_workspace",
        default="",
    ) or ""
    compact_note = safe_best_effort(
        lambda: format_compaction_status_line(health).replace("压缩状态: ", ""),
        label="health_report.compaction_status",
        default="",
    ) or ""
    if not compact_note:
        if health.get("hygiene_compressed"):
            compact_note = "是"
        elif health.get("context_compact_circuit_open"):
            compact_note = "熔断跳过"
        elif health.get("hygiene_compact_skipped"):
            compact_note = f"跳过({health.get('hygiene_compact_skipped')})"
        else:
            compact_note = "否"

    stale_lines = safe_best_effort(
        lambda: delegate_stale_lines(health, inp.session_key),
        label="health_report.delegate_stale",
        default=[],
    ) or []
    recovery_lines = safe_best_effort(
        lambda: recovery_bucket_lines(health, inp.session_key),
        label="health_report.recovery_buckets",
        default=[],
    ) or []
    from butler import get_build_identity

    bi = get_build_identity()
    _start_ts = bi.get("start_time", "")
    _uptime = ""
    if _start_ts:
        import datetime

        try:
            _st = datetime.datetime.fromisoformat(_start_ts)
            _delta = datetime.datetime.now(tz=datetime.timezone.utc) - _st
            _h, _rem = divmod(int(_delta.total_seconds()), 3600)
            _m = _rem // 60
            _uptime = f"{_h}h {_m}m"
        except Exception:
            pass

    out: list[str] = [
        "Butler 诊断",
        f"版本: {bi['version']} ({bi['git_sha']})",
        f"Python: {bi['python']} ({bi['python_path']})",
    ]
    if _uptime:
        out.append(f"运行时长: {_uptime}")
    out += [
        f"会话: {health.get('session_key') or inp.session_key}",
        f"平台: {health.get('platform') or '-'}",
        engine_line,
        context_line,
        context_config_line,
    ]
    if workspace_line:
        out.append(workspace_line)
    out += [
        f"记忆提炼模型(post_session): {aux_label}",
        f"压缩: {compact_note}",
    ]
    fact_line = safe_best_effort(
        lambda: format_fact_survival_line(health),
        label="health_report.fact_survival",
        default="",
    )
    if fact_line:
        out.append(fact_line)
    out += [
        f"Schema 降级: {'是' if schema_recovered else '否'}",
        f"剥离关键字: {schema_keywords}",
        f"Skill: {'已注入' if health.get('skill_context_injected') else '未注入'}",
        f"命中 Skill: {', '.join(str(s) for s in skill_matches) if skill_matches else '-'}",
        f"记忆上下文: {'已注入' if health.get('memory_context_injected') else '未注入'}",
        f"记忆同步: {'已同步' if not memory_sync.get('skipped', True) else '跳过'}",
        f"Provider 同步: {'是' if memory_sync.get('provider_synced') else '否'}",
    ]
    error_count = int(health.get("error_count") or 0)
    out.append(f"运行时错误计数: {error_count}")
    metrics_line = safe_best_effort(
        lambda: runtime_metrics_line(),
        label="health_report.runtime_metrics_line",
        default="",
    )
    if metrics_line:
        out.append(metrics_line)
    out.extend(stale_lines + recovery_lines + hook_lines_fn(inp.session_key, health))
    out.extend(
        safe_best_effort(
            lambda: format_pipeline_step_lines(health),
            label="health_report.pipeline_steps",
            default=[],
        )
        or []
    )
    out.extend(
        safe_best_effort(
            lambda: stream_probe_turn_lines(inp.orchestrator),
            label="health_report.stream_probe_turn",
            default=[],
        )
        or []
    )
    schema_line = safe_best_effort(
        lambda: schema_optimize_line(health, loop_health),
        label="health_report.schema_optimize",
        default="",
    )
    if schema_line:
        out.append(schema_line)
    return out


__all__ = [
    "delegate_stale_lines",
    "recovery_bucket_lines",
    "runtime_metrics_line",
    "schema_optimize_line",
    "stream_probe_turn_lines",
    "turn_diagnostic_lines",
]
