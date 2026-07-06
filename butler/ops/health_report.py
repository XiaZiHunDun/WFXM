"""Build ``/health`` and ``/诊断`` text from orchestrator + session snapshots."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast
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


def _append_diag_lines(lines: list[str], label: str, fn: Callable[[], list[str]]) -> None:
    extra = safe_best_effort(fn, label=f"health_report.{label}", default=[])
    if extra:
        lines.extend(extra)


def format_build_uptime(start_ts: str) -> str:
    if not start_ts:
        return ""

    def _run() -> str:
        import datetime

        st = datetime.datetime.fromisoformat(start_ts)
        delta = datetime.datetime.now(tz=datetime.timezone.utc) - st
        hours, rem = divmod(int(delta.total_seconds()), 3600)
        minutes = rem // 60
        return f"{hours}h {minutes}m"

    result = safe_best_effort(_run, label="health_report.build_uptime", default="")
    return result if isinstance(result, str) else ""


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
        return cast(dict[str, Any], mem_stats)

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
    return cast(dict[str, Any], mem_stats)


def collect_approval_stats_for_health(session_key: str) -> dict[str, Any]:
    """Sprint 24 P1-3.2: /诊断 集成 — 读 session approvals.json 统计."""
    def _load() -> dict[str, Any]:
        from butler.permissions.approvals import summarize_approvals

        return cast(dict[str, Any], summarize_approvals(session_key))

    result = safe_best_effort(
        _load,
        label="health_report.approval_stats",
        default=_EMPTY_APPROVAL_STATS,
    )
    return result if isinstance(result, dict) else _EMPTY_APPROVAL_STATS


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

        return cast(list[str], format_rag_diagnostic_lines(inp.mem_stats, session_key=inp.session_key))

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

        return cast(list[str], format_experiment_diagnostic_lines(Path(proj.workspace)))

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

        return cast(list[str], format_usage_ledger_lines())

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

        return cast(list[str], format_stream_probe_lines())

    _append_diag_lines(lines, "stream_probe", _stream_probe_lines)

    def _circuit_lines() -> list[str]:
        from butler.transport.provider_health import format_circuit_diagnostic_lines

        return cast(list[str], format_circuit_diagnostic_lines())

    _append_diag_lines(lines, "provider_circuit", _circuit_lines)
    return lines


def _format_hook_lines(session_key: str) -> list[str]:
    from butler.hooks.telemetry import format_hook_diagnostic_lines

    return cast(list[str], format_hook_diagnostic_lines(session_key))


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
    h = health or {}
    loop_raw = h.get("loop")
    loop: dict[str, Any] = loop_raw if isinstance(loop_raw, dict) else {}
    trans = h.get("loop_transition_reason") or loop.get("loop_transition_reason") or ""
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
    stop_ctx = loop.get("stop_hook_context")
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
    return cast(list[str], format_outbound_diagnostic_lines(session_key, chat_id=chat_id))


def _harness_diagnostic_lines(
    health: dict[str, Any] | None,
    session_key: str,
) -> list[str]:
    from butler.ops.harness_diagnostics import format_harness_diagnostic_lines

    return cast(list[str], format_harness_diagnostic_lines(health, session_key=session_key))


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
    return cast(
        list[str],
        format_token_cost_diagnostic_lines(
        health,
        model=model_name,
        estimate_cost=token_cost_estimate_enabled(),
        ),
    )


def _transcript_lines(session_key: str) -> list[str]:
    from butler.ops.transcript_diagnostics import format_transcript_diagnostic_lines

    return cast(list[str], format_transcript_diagnostic_lines(session_key))


def _metrics_diag_lines(session_key: str) -> list[str]:
    from butler.ops.runtime_metrics import format_metrics_diagnostic_lines

    return cast(list[str], format_metrics_diagnostic_lines(session_key=session_key))


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

    report_lines: list[str] = []
    if health:
        from butler.ops.health_report_turn import turn_diagnostic_lines

        report_lines.extend(
            turn_diagnostic_lines(inp, hook_lines_fn=_hook_diagnostic_lines)
        )
        report_lines.extend(_shared_diagnostic_lines(inp, use_mem_stats_project_name=True))
        if health.get("error"):
            report_lines.append("错误: 有（查看日志）")
        if health.get("hygiene_error"):
            report_lines.append("压缩错误: 有（查看日志）")
        report_lines.extend(
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
        report_lines = [
            "Butler 诊断",
            f"版本: {_bi2['version']} ({_bi2['git_sha']})",
            f"会话: {inp.session_key}",
            format_context_budget_line({}),
            "轮次诊断: 暂无（本会话尚无完整对话轮次）",
        ]
        report_lines.extend(_shared_diagnostic_lines(inp))

    report_lines.extend(_hook_diagnostic_lines(inp.session_key, health))
    report_lines.extend(_tool_audit_lines(tool_summary))
    report_lines.extend(
        safe_best_effort(
            lambda: _transcript_lines(inp.session_key),
            label="health_report.transcript",
            default=[],
        )
        or []
    )
    report_lines.extend(
        safe_best_effort(
            lambda: _metrics_diag_lines(inp.session_key),
            label="health_report.metrics",
            default=[],
        )
        or []
    )
    return "\n".join(report_lines)
