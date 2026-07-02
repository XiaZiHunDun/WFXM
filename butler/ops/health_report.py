"""Build ``/health`` and ``/诊断`` text from orchestrator + session snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging


from butler.core.best_effort import safe_best_effort

logger = logging.getLogger(__name__)

_EMPTY_APPROVAL_STATS: dict[str, Any] = {
    "always_count": 0,
    "once_active_count": 0,
    "has_pending": False,
    "external_directory_always_count": 0,
    "external_directory_once_count": 0,
}


def _append_diag_lines(lines: list[str], label: str, fn) -> None:
    extra = safe_best_effort(fn, label=f"health_report.{label}", default=[])
    if extra:
        lines.extend(extra)

@dataclass
class HealthReportInput:
    session_key: str
    health: dict[str, Any] | None
    tool_summary: dict[str, Any]
    mem_stats: dict[str, Any]
    orchestrator: Any


def collect_mem_stats_for_health(
    orchestrator: Any,
    session_key: str,
    health: dict[str, Any] | None,
) -> dict[str, Any]:
    from butler.memory.diagnostics import collect_memory_layer_stats

    mem_stats = collect_memory_layer_stats(orchestrator, session_key=session_key)
    if not health:
        return mem_stats

    if health.get("memory_prefetch_chars") is not None:
        mem_stats["last_prefetch_chars"] = health.get("memory_prefetch_chars")
    elif health.get("memory_context_chars") is not None:
        mem_stats["last_prefetch_chars"] = health.get("memory_context_chars")
    if "memory_prefetch_cache_hit" in health:
        mem_stats["memory_prefetch_cache_hit"] = health.get("memory_prefetch_cache_hit")
    last_q = str(health.get("last_user_query") or "").strip()
    if last_q:
        from butler.memory.prefetch_cache import get_cached_prefetch

        mem_stats["last_user_query"] = last_q
        mem_stats["memory_prefetch_cache_ready"] = (
            get_cached_prefetch(session_key, last_q) is not None
        )
    if health.get("memory_project_prefetch_mode"):
        mem_stats["memory_project_prefetch_mode"] = health.get(
            "memory_project_prefetch_mode"
        )
    return mem_stats


def collect_approval_stats_for_health(session_key: str) -> dict[str, Any]:
    """Sprint 24 P1-3.2: /诊断 集成 — 读 session approvals.json 统计."""
    def _load() -> dict[str, Any]:
        from butler.permissions.approvals import summarize_approvals

        return summarize_approvals(session_key)

    result = safe_best_effort(
        _load,
        label="health_report.approval_stats",
        default=_EMPTY_APPROVAL_STATS,
    )
    return result if isinstance(result, dict) else _EMPTY_APPROVAL_STATS


def _recovery_bucket_lines(health: dict[str, Any], session_key: str) -> list[str]:
    from butler.ops.retry_buckets import format_recovery_bucket_lines

    return format_recovery_bucket_lines(
        session_key=health.get("session_key") or session_key,
    )


def _delegate_stale_lines(health: dict[str, Any], session_key: str) -> list[str]:
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


def _shared_diagnostic_lines(
    inp: HealthReportInput,
    *,
    use_mem_stats_project_name: bool = False,
) -> list[str]:
    from butler.memory.diagnostics import format_memory_diagnostic_lines
    from butler.model_resolve import format_model_diagnostic_lines
    from butler.ops.snapshot import format_ops_diagnostic_lines
    from butler.project.meta import (
        format_default_project_policy_lines,
        format_project_meta_lines,
    )
    from butler.runtime.diagnostics import format_runtime_diagnostic_lines

    lines: list[str] = []

    def _degradation_lines() -> list[str]:
        from butler.ops.degradation_registry import (
            enrich_stats_with_live_mcp,
            format_diagnostic_lines,
            sync_compaction_acl_from_metrics,
            sync_memory_degradations_from_stats,
        )

        sync_compaction_acl_from_metrics()
        enriched = enrich_stats_with_live_mcp(
            inp.mem_stats,
            session_key=inp.session_key,
        )
        inp.mem_stats.clear()
        inp.mem_stats.update(enriched)
        sync_memory_degradations_from_stats(inp.mem_stats)
        deg = format_diagnostic_lines()
        return (deg + [""]) if deg else []

    _append_diag_lines(lines, "degradation", _degradation_lines)
    lines.extend(format_memory_diagnostic_lines(inp.mem_stats))
    # Sprint 24 P1-3.2: 权限批准缓存统计
    def _approval_lines() -> list[str]:
        approval_stats = collect_approval_stats_for_health(inp.session_key)
        out = [
            "权限批准缓存:",
            (
                f"  始终允许 {approval_stats['always_count']} 项 · "
                f"本次允许 {approval_stats['once_active_count']} 项"
            ),
        ]
        if approval_stats["has_pending"]:
            out.append("  ⏳ 有 1 项待批准")
        ext_always = int(approval_stats.get("external_directory_always_count") or 0)
        ext_once = int(approval_stats.get("external_directory_once_count") or 0)
        if ext_always or ext_once or approval_stats.get("has_pending"):
            out.append("External-Dir:")
            out.append(
                f"  always={ext_always} · once={ext_once}"
                f" · pending={'Y' if approval_stats.get('has_pending') else 'N'}"
            )
        return out

    _append_diag_lines(lines, "approval", _approval_lines)
    lines.extend(
        format_default_project_policy_lines(inp.orchestrator, inp.session_key)
    )
    proj = inp.orchestrator.project_manager.get_current(session_key=inp.session_key)
    if proj is not None:
        lines.append("项目元数据:")
        lines.extend(format_project_meta_lines(proj))
    proj_name = ""
    if use_mem_stats_project_name:
        proj_name = str(inp.mem_stats.get("project_name") or "").strip()
    if not proj_name and proj is not None:
        proj_name = str(getattr(proj, "name", "") or "")
    lines.extend(format_runtime_diagnostic_lines(proj_name))
    lines.extend(
        format_model_diagnostic_lines(
            project=proj,
            settings=inp.orchestrator._settings,
        )
    )
    lines.extend(format_ops_diagnostic_lines())

    def _rag_lines() -> list[str]:
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        return format_rag_diagnostic_lines(inp.mem_stats, session_key=inp.session_key)

    _append_diag_lines(lines, "rag", _rag_lines)

    def _execution_surface_lines() -> list[str]:
        from butler.ops.execution_surface_diagnostics import (
            collect_execution_surface_stats,
            format_execution_surface_diagnostic_lines,
        )

        es_stats = collect_execution_surface_stats(
            inp.orchestrator,
            health=inp.health,
            session_key=inp.session_key,
        )
        es_lines = format_execution_surface_diagnostic_lines(
            es_stats, session_key=inp.session_key
        )
        return ["", *es_lines] if es_lines else []

    _append_diag_lines(lines, "execution_surface", _execution_surface_lines)

    def _stack_lines() -> list[str]:
        if proj is None:
            return []
        from butler.ops.stack_diagnostics import format_stack_diagnostic_lines

        stack_lines = format_stack_diagnostic_lines(Path(proj.workspace))
        return ["", *stack_lines] if stack_lines else []

    _append_diag_lines(lines, "stack", _stack_lines)

    def _experiment_lines() -> list[str]:
        if proj is None:
            return []
        from butler.ops.experiment_diagnostics import format_experiment_diagnostic_lines

        return format_experiment_diagnostic_lines(Path(proj.workspace))

    _append_diag_lines(lines, "experiment", _experiment_lines)

    def _observation_lines() -> list[str]:
        if proj is None:
            return []
        from butler.ops.observation_diagnostics import format_observation_diagnostic_lines

        obs_lines = format_observation_diagnostic_lines(Path(proj.workspace))
        return ["", *obs_lines] if obs_lines else []

    _append_diag_lines(lines, "observation", _observation_lines)

    def _usage_lines() -> list[str]:
        from butler.ops.usage_ledger import format_usage_ledger_lines

        return format_usage_ledger_lines()

    _append_diag_lines(lines, "usage_ledger", _usage_lines)

    def _calibration_lines() -> list[str]:
        from butler.ops.cost_calibration import format_rollup_lines

        cal = format_rollup_lines()
        return ["", *cal] if cal else []

    _append_diag_lines(lines, "cost_calibration", _calibration_lines)

    def _eval_lines() -> list[str]:
        from butler.ops.eval_diagnostics import format_eval_quality_lines

        eq = format_eval_quality_lines()
        return ["", *eq] if eq else []

    _append_diag_lines(lines, "eval_quality", _eval_lines)

    def _boundary_lines() -> list[str]:
        from butler.ops.boundary_observability import format_boundary_observability_lines

        bo = format_boundary_observability_lines()
        return ["", *bo] if bo else []

    _append_diag_lines(lines, "boundary_obs", _boundary_lines)

    def _stream_probe_lines() -> list[str]:
        from butler.transport.stream_probe import format_stream_probe_lines

        return format_stream_probe_lines()

    _append_diag_lines(lines, "stream_probe", _stream_probe_lines)

    def _circuit_lines() -> list[str]:
        from butler.transport.provider_health import format_circuit_diagnostic_lines

        return format_circuit_diagnostic_lines()

    _append_diag_lines(lines, "provider_circuit", _circuit_lines)
    return lines


def _turn_diagnostic_lines(inp: HealthReportInput) -> list[str]:
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
        lambda: _delegate_stale_lines(health, inp.session_key),
        label="health_report.delegate_stale",
        default=[],
    ) or []
    recovery_lines = safe_best_effort(
        lambda: _recovery_bucket_lines(health, inp.session_key),
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
        lambda: _runtime_metrics_line(),
        label="health_report.runtime_metrics_line",
        default="",
    )
    if metrics_line:
        out.append(metrics_line)
    out.extend(stale_lines + recovery_lines + _hook_diagnostic_lines(inp.session_key, health))
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
            lambda: _stream_probe_turn_lines(inp.orchestrator),
            label="health_report.stream_probe_turn",
            default=[],
        )
        or []
    )
    schema_line = safe_best_effort(
        lambda: _schema_optimize_line(health, loop_health),
        label="health_report.schema_optimize",
        default="",
    )
    if schema_line:
        out.append(schema_line)
    return out


def _format_hook_lines(session_key: str) -> list[str]:
    from butler.hooks.telemetry import format_hook_diagnostic_lines

    return format_hook_diagnostic_lines(session_key)


def _runtime_metrics_line() -> str:
    from butler.ops.runtime_metrics import get_runtime_metrics

    metrics = get_runtime_metrics()
    compaction_count = metrics.get("compaction_count", 0)
    token_estimate = metrics.get("context_token_estimate", "-")
    return f"Context Pipeline: compaction={compaction_count}, tokens≈{token_estimate}"


def _stream_probe_turn_lines(orchestrator: Any) -> list[str]:
    from butler.transport.stream_probe import (
        format_stream_probe_lines,
        run_stream_probe,
        stream_probe_enabled,
    )

    if not stream_probe_enabled():
        return []
    run_stream_probe(orchestrator)
    return format_stream_probe_lines()


def _schema_optimize_line(health: dict[str, Any], loop_health: dict[str, Any]) -> str:
    from butler.core.schema_optimizer import schema_optimize_enabled

    if not schema_optimize_enabled():
        return ""
    stripped = health.get("schema_optimize_stripped") or loop_health.get(
        "schema_optimize_stripped"
    )
    if not stripped:
        return ""
    return f"Schema 预优化剥离: {int(stripped)}"


def _hook_diagnostic_lines(session_key: str, health: dict[str, Any] | None) -> list[str]:
    lines: list[str] = []
    hook_lines = safe_best_effort(
        lambda: _format_hook_lines(session_key),
        label="health_report.hook_telemetry",
        default=None,
    )
    if hook_lines is None:
        lines.append("Shell hooks: 不可用")
    else:
        lines.extend(hook_lines)
    loop = (health or {}).get("loop") if isinstance((health or {}).get("loop"), dict) else {}
    trans = (health or {}).get("loop_transition_reason") or (
        loop.get("loop_transition_reason") if isinstance(loop, dict) else ""
    )
    if trans:
        lines.append(f"上轮循环结束: {trans}")
    if loop.get("stop_hook_blocked"):
        lines.append("Stop 钩子: 已阻断收尾")
    if (health or {}).get("turn_token_budget"):
        lines.append(
            f"上轮 token 预算: {(health or {})['turn_token_budget']:,} "
            f"(max_iter={(health or {}).get('turn_max_iterations', '-')})"
        )
    queue_lines = safe_best_effort(
        lambda: _queue_diagnostic_lines(session_key),
        label="health_report.queue_status",
        default=[],
    )
    lines.extend(queue_lines or [])
    stop_ctx = loop.get("stop_hook_context") if isinstance(loop, dict) else None
    if stop_ctx:
        if isinstance(stop_ctx, list):
            preview = " | ".join(str(x)[:80] for x in stop_ctx[:2])
        else:
            preview = str(stop_ctx)[:160]
        lines.append(f"上轮 Stop 注入: {preview}")
    outbound_lines = safe_best_effort(
        lambda: _outbound_diagnostic_lines(session_key, health),
        label="health_report.outbound_policy",
        default=None,
    )
    if outbound_lines is None:
        lines.append("出站策略: 不可用")
    else:
        lines.extend(outbound_lines)
    harness_lines = safe_best_effort(
        lambda: _harness_diagnostic_lines(health, session_key),
        label="health_report.harness",
        default=[],
    )
    if harness_lines:
        lines.append("Harness 对标 (OpenClaw + OMO):")
        lines.extend(f"  {ln}" for ln in harness_lines)
    return lines


def _queue_diagnostic_lines(session_key: str) -> list[str]:
    from butler.gateway.message_queue import pending_count
    from butler.gateway.queue_settings import format_queue_status_line

    out: list[str] = []
    pending = pending_count(session_key)
    if pending:
        out.append(f"入站队列待发: {pending} 条")
    out.append(format_queue_status_line(session_key))
    return out


def _outbound_diagnostic_lines(
    session_key: str,
    health: dict[str, Any] | None,
) -> list[str]:
    from butler.gateway.completion_notify import format_outbound_diagnostic_lines

    chat_id = ""
    if health:
        chat_id = str(health.get("platform_chat_id") or health.get("chat_id") or "")
    return format_outbound_diagnostic_lines(session_key, chat_id=chat_id)


def _harness_diagnostic_lines(
    health: dict[str, Any] | None,
    session_key: str,
) -> list[str]:
    from butler.ops.harness_diagnostics import format_harness_diagnostic_lines

    return format_harness_diagnostic_lines(health, session_key=session_key)


def _token_cost_lines(inp: HealthReportInput, health: dict[str, Any]) -> list[str]:
    from butler.model_resolve import resolve_effective_model
    from butler.ops.token_cost_diagnostics import (
        format_token_cost_diagnostic_lines,
        token_cost_estimate_enabled,
    )

    model_name = safe_best_effort(
        lambda: str(
            resolve_effective_model(
                "butler",
                project=inp.orchestrator.project_manager.get_current(
                    session_key=inp.session_key
                ),
                settings=inp.orchestrator._settings,
            ).config.model
            or ""
        ),
        label="health_report.token_cost_model",
        default="",
    ) or ""
    return format_token_cost_diagnostic_lines(
        health,
        model=model_name,
        estimate_cost=token_cost_estimate_enabled(),
    )


def _transcript_lines(session_key: str) -> list[str]:
    from butler.ops.transcript_diagnostics import format_transcript_diagnostic_lines

    return format_transcript_diagnostic_lines(session_key)


def _metrics_diag_lines(session_key: str) -> list[str]:
    from butler.ops.runtime_metrics import format_metrics_diagnostic_lines

    return format_metrics_diagnostic_lines(session_key=session_key)


def _tool_audit_lines(tool_summary: dict[str, Any]) -> list[str]:
    if not tool_summary.get("total"):
        return []
    return [
        f"工具调用: {tool_summary['total']}",
        f"工具失败: {tool_summary['failed']}",
        f"工具错误码: {', '.join(tool_summary['codes']) if tool_summary['codes'] else '-'}",
    ]


def build_health_report(inp: HealthReportInput) -> str:
    """Format diagnostic report (behavior-stable with legacy ``_format_health_summary``)."""
    health = inp.health
    tool_summary = inp.tool_summary

    if not health and not tool_summary.get("total"):
        from butler import get_build_identity
        from butler.core.context_budget import format_context_budget_line

        _bi = get_build_identity()
        lines = [
            "Butler 诊断",
            f"版本: {_bi['version']} ({_bi['git_sha']})",
            f"会话: {inp.session_key}",
            format_context_budget_line(health or {}),
            "轮次诊断: 暂无（本会话尚无完整对话轮次）",
        ]
        lines.extend(_shared_diagnostic_lines(inp))
        lines.extend(_hook_diagnostic_lines(inp.session_key, health))
        lines.extend(
            safe_best_effort(
                lambda: _transcript_lines(inp.session_key),
                label="health_report.transcript",
                default=[],
            )
            or []
        )
        lines.extend(
            safe_best_effort(
                lambda: _metrics_diag_lines(inp.session_key),
                label="health_report.metrics",
                default=[],
            )
            or []
        )
        return "\n".join(lines)

    lines: list[str] = []
    if health:
        lines.extend(_turn_diagnostic_lines(inp))
        lines.extend(_shared_diagnostic_lines(inp, use_mem_stats_project_name=True))
        if health.get("error"):
            lines.append("错误: 有（查看日志）")
        if health.get("hygiene_error"):
            lines.append("压缩错误: 有（查看日志）")
        lines.extend(
            safe_best_effort(
                lambda: _token_cost_lines(inp, health),
                label="health_report.token_cost",
                default=[],
            )
            or []
        )
    else:
        from butler import get_build_identity
        from butler.core.context_budget import format_context_budget_line

        _bi2 = get_build_identity()
        lines = [
            "Butler 诊断",
            f"版本: {_bi2['version']} ({_bi2['git_sha']})",
            f"会话: {inp.session_key}",
            format_context_budget_line({}),
            "轮次诊断: 暂无（本会话尚无完整对话轮次）",
        ]
        lines.extend(_shared_diagnostic_lines(inp))

    lines.extend(_hook_diagnostic_lines(inp.session_key, health))
    lines.extend(_tool_audit_lines(tool_summary))
    lines.extend(
        safe_best_effort(
            lambda: _transcript_lines(inp.session_key),
            label="health_report.transcript",
            default=[],
        )
        or []
    )
    lines.extend(
        safe_best_effort(
            lambda: _metrics_diag_lines(inp.session_key),
            label="health_report.metrics",
            default=[],
        )
        or []
    )
    return "\n".join(lines)
