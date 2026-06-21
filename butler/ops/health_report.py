"""Build ``/health`` and ``/诊断`` text from orchestrator + session snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import logging


logger = logging.getLogger(__name__)

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
    """Sprint 24 P1-3.2: /诊断 集成 — 读 session approvals.json 统计.

    返回 dict 形如: {always_count, once_active_count, has_pending,
    external_directory_always_count, external_directory_once_count}.
    与 collect_mem_stats_for_health 平行, 在 _shared_diagnostic_lines 中调用.
    """
    try:
        from butler.permissions.approvals import summarize_approvals

        return summarize_approvals(session_key)
    except Exception as exc:
        logger.debug("collect approval stats skipped: %s", exc)
        return {
            "always_count": 0,
            "once_active_count": 0,
            "has_pending": False,
            "external_directory_always_count": 0,
            "external_directory_once_count": 0,
        }


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
    lines.extend(format_memory_diagnostic_lines(inp.mem_stats))
    # Sprint 24 P1-3.2: 权限批准缓存统计
    try:
        approval_stats = collect_approval_stats_for_health(inp.session_key)
        lines.append("权限批准缓存:")
        lines.append(
            f"  始终允许 {approval_stats['always_count']} 项 · "
            f"本次允许 {approval_stats['once_active_count']} 项"
        )
        if approval_stats["has_pending"]:
            lines.append("  ⏳ 有 1 项待批准")
        # Sprint 27 P1-3.3: external_directory 决策透传. 仅当有活动时输出,
        # 避免无 external_directory 活动时的无谓噪声行.
        ext_always = int(approval_stats.get("external_directory_always_count") or 0)
        ext_once = int(approval_stats.get("external_directory_once_count") or 0)
        if ext_always or ext_once or approval_stats.get("has_pending"):
            lines.append("External-Dir:")
            lines.append(
                f"  always={ext_always} · once={ext_once}"
                f" · pending={'Y' if approval_stats.get('has_pending') else 'N'}"
            )
    except Exception as exc:
        logger.debug("approval diagnostic lines skipped: %s", exc)
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
    try:
        from butler.ops.rag_diagnostics import format_rag_diagnostic_lines

        lines.extend(
            format_rag_diagnostic_lines(inp.mem_stats, session_key=inp.session_key)
        )
    except Exception as exc:
        logger.debug("shared diagnostic lines skipped: %s", exc)
    try:
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
        if es_lines:
            lines.append("")
            lines.extend(es_lines)
    except Exception as exc:
        logger.debug("execution surface diagnostic lines skipped: %s", exc)
    try:
        from butler.ops.stack_diagnostics import format_stack_diagnostic_lines

        if proj is not None:
            stack_lines = format_stack_diagnostic_lines(Path(proj.workspace))
            if stack_lines:
                lines.append("")
                lines.extend(stack_lines)
    except Exception as exc:
        logger.debug("stack diagnostic lines skipped: %s", exc)
    try:
        from butler.ops.experiment_diagnostics import format_experiment_diagnostic_lines

        if proj is not None:
            lines.extend(format_experiment_diagnostic_lines(Path(proj.workspace)))
    except Exception as exc:
        logger.debug("shared diagnostic lines skipped: %s", exc)
    try:
        from butler.ops.usage_ledger import format_usage_ledger_lines

        lines.extend(format_usage_ledger_lines())
    except Exception as exc:
        logger.debug("shared diagnostic lines skipped: %s", exc)
    try:
        from butler.ops.cost_calibration import format_rollup_lines

        cal = format_rollup_lines()
        if cal:
            lines.append("")
            lines.extend(cal)
    except Exception as exc:
        logger.debug("shared diagnostic lines skipped: %s", exc)
    try:
        from butler.ops.eval_diagnostics import format_eval_quality_lines

        eq = format_eval_quality_lines()
        if eq:
            lines.append("")
            lines.extend(eq)
    except Exception as exc:
        logger.debug("eval quality diagnostic lines skipped: %s", exc)
    try:
        from butler.ops.boundary_observability import format_boundary_observability_lines

        bo = format_boundary_observability_lines()
        if bo:
            lines.append("")
            lines.extend(bo)
    except Exception as exc:
        logger.debug("boundary observability lines skipped: %s", exc)
    try:
        from butler.transport.stream_probe import format_stream_probe_lines

        lines.extend(format_stream_probe_lines())
    except Exception as exc:
        logger.debug("shared diagnostic lines skipped: %s", exc)
    try:
        from butler.transport.provider_health import format_circuit_diagnostic_lines

        lines.extend(format_circuit_diagnostic_lines())
    except Exception as exc:
        logger.debug("shared diagnostic lines skipped: %s", exc)
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

    try:
        aux = resolve_auxiliary_config("post_session")
        aux_label = f"{aux.provider or '?'}/{aux.model or '?'}"
    except Exception:
        aux_label = "未配置"

    from butler.project.lead import lead_mode_banner_line

    agent_role = str(health.get("gateway_agent_role") or "butler")
    engine_line = (
        lead_mode_banner_line()
        if agent_role == "lead"
        else "对话引擎: 管家 Butler"
    )
    from butler.core.context_budget import format_context_budget_line
    from butler.context_settings import format_context_config_source_line

    context_line = format_context_budget_line(health)
    context_config_line = format_context_config_source_line()
    try:
        from butler.tools.path_safety import format_tool_workspace_line

        workspace_line = format_tool_workspace_line(
            str(health.get("session_key") or inp.session_key or "")
        )
    except Exception:
        workspace_line = ""
    try:
        from butler.core.compaction_status import format_compaction_status_line

        compact_note = format_compaction_status_line(health).replace("压缩状态: ", "")
    except Exception:
        compact_note = "否"
        if health.get("hygiene_compressed"):
            compact_note = "是"
        elif health.get("context_compact_circuit_open"):
            compact_note = "熔断跳过"
        elif health.get("hygiene_compact_skipped"):
            compact_note = f"跳过({health.get('hygiene_compact_skipped')})"

    stale_lines: list[str] = []
    try:
        from butler.runtime.task_store import mark_stale_tasks, count_running_tasks

        stale = mark_stale_tasks(health.get("session_key") or inp.session_key, auto_fail=False)
        running = count_running_tasks(health.get("session_key") or inp.session_key)
        if running:
            stale_lines.append(f"委派 running: {running}")
        if stale:
            stale_lines.append(f"委派 stale: {len(stale)}（>阈值未结束）")
            for row in stale[:3]:
                stale_lines.append(
                    f"  ⏱ {row.get('task_id')} {(row.get('task_preview') or '')[:40]}"
                )
    except Exception as exc:
        logger.debug("turn diagnostic lines skipped: %s", exc)
    recovery_lines: list[str] = []
    try:
        from butler.ops.retry_buckets import format_recovery_bucket_lines

        recovery_lines = format_recovery_bucket_lines(
            session_key=health.get("session_key") or inp.session_key,
        )
    except Exception as exc:
        logger.debug("turn diagnostic lines skipped: %s", exc)
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
    try:
        from butler.core.compaction_status import format_fact_survival_line

        fact_line = format_fact_survival_line(health)
        if fact_line:
            out.append(fact_line)
    except Exception as exc:
        logger.debug("fact survival diagnostic line skipped: %s", exc)
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
    try:
        from butler.ops.runtime_metrics import get_runtime_metrics

        metrics = get_runtime_metrics()
        compaction_count = metrics.get("compaction_count", 0)
        token_estimate = metrics.get("context_token_estimate", "-")
        out.append(f"Context Pipeline: compaction={compaction_count}, tokens≈{token_estimate}")
    except Exception:
        pass
    out.extend(stale_lines + recovery_lines + _hook_diagnostic_lines(inp.session_key, health))
    try:
        from butler.core.pipeline_steps import format_pipeline_step_lines

        out.extend(format_pipeline_step_lines(health))
    except Exception as exc:
        logger.debug("turn diagnostic lines skipped: %s", exc)
    try:
        from butler.transport.stream_probe import (
            format_stream_probe_lines,
            run_stream_probe,
            stream_probe_enabled,
        )

        if stream_probe_enabled():
            run_stream_probe(inp.orchestrator)
            out.extend(format_stream_probe_lines())
    except Exception as exc:
        logger.debug("turn diagnostic lines skipped: %s", exc)
    try:
        from butler.core.schema_optimizer import schema_optimize_enabled

        if schema_optimize_enabled():
            stripped = health.get("schema_optimize_stripped") or loop_health.get(
                "schema_optimize_stripped"
            )
            if stripped:
                out.append(f"Schema 预优化剥离: {int(stripped)}")
    except Exception as exc:
        logger.debug("turn diagnostic lines skipped: %s", exc)
    return out


def _hook_diagnostic_lines(session_key: str, health: dict[str, Any] | None) -> list[str]:
    lines: list[str] = []
    try:
        from butler.hooks.telemetry import format_hook_diagnostic_lines

        lines.extend(format_hook_diagnostic_lines(session_key))
    except Exception:
        lines.append("Shell hooks: 不可用")
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
    try:
        from butler.gateway.message_queue import pending_count

        pending = pending_count(session_key)
        if pending:
            lines.append(f"入站队列待发: {pending} 条")
        from butler.gateway.queue_settings import format_queue_status_line

        lines.append(format_queue_status_line(session_key))
    except Exception as exc:
        logger.debug("hook diagnostic lines skipped: %s", exc)
    stop_ctx = loop.get("stop_hook_context") if isinstance(loop, dict) else None
    if stop_ctx:
        if isinstance(stop_ctx, list):
            preview = " | ".join(str(x)[:80] for x in stop_ctx[:2])
        else:
            preview = str(stop_ctx)[:160]
        lines.append(f"上轮 Stop 注入: {preview}")
    try:
        from butler.gateway.completion_notify import format_outbound_diagnostic_lines

        chat_id = ""
        if health:
            chat_id = str(health.get("platform_chat_id") or health.get("chat_id") or "")
        lines.extend(format_outbound_diagnostic_lines(session_key, chat_id=chat_id))
    except Exception:
        lines.append("出站策略: 不可用")
    try:
        from butler.ops.harness_diagnostics import format_harness_diagnostic_lines

        oc_lines = format_harness_diagnostic_lines(health, session_key=session_key)
        if oc_lines:
            lines.append("Harness 对标 (OpenClaw + OMO):")
            lines.extend(f"  {ln}" for ln in oc_lines)
    except Exception as exc:
        logger.debug("hook diagnostic lines skipped: %s", exc)
    return lines


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
        try:
            from butler.ops.transcript_diagnostics import format_transcript_diagnostic_lines

            lines.extend(format_transcript_diagnostic_lines(inp.session_key))
        except Exception as exc:
            logger.debug("build health report skipped: %s", exc)
        try:
            from butler.ops.runtime_metrics import format_metrics_diagnostic_lines

            lines.extend(format_metrics_diagnostic_lines(session_key=inp.session_key))
        except Exception as exc:
            logger.debug("build health report skipped: %s", exc)
        return "\n".join(lines)

    lines: list[str] = []
    if health:
        lines.extend(_turn_diagnostic_lines(inp))
        lines.extend(_shared_diagnostic_lines(inp, use_mem_stats_project_name=True))
        if health.get("error"):
            lines.append("错误: 有（查看日志）")
        if health.get("hygiene_error"):
            lines.append("压缩错误: 有（查看日志）")
        try:
            from butler.ops.token_cost_diagnostics import (
                format_token_cost_diagnostic_lines,
                token_cost_estimate_enabled,
            )
            from butler.model_resolve import resolve_effective_model

            model_name = ""
            try:
                proj = inp.orchestrator.project_manager.get_current(session_key=inp.session_key)
                em = resolve_effective_model(
                    "butler", project=proj, settings=inp.orchestrator._settings
                )
                model_name = str(em.config.model or "")
            except Exception as exc:
                logger.debug("build health report skipped: %s", exc)
            lines.extend(
                format_token_cost_diagnostic_lines(
                    health,
                    model=model_name,
                    estimate_cost=token_cost_estimate_enabled(),
                )
            )
        except Exception as exc:
            logger.debug("build health report skipped: %s", exc)
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
    try:
        from butler.ops.transcript_diagnostics import format_transcript_diagnostic_lines

        lines.extend(format_transcript_diagnostic_lines(inp.session_key))
    except Exception as exc:
        logger.debug("build health report skipped: %s", exc)
    try:
        from butler.ops.runtime_metrics import format_metrics_diagnostic_lines

        lines.extend(format_metrics_diagnostic_lines(session_key=inp.session_key))
    except Exception as exc:
        logger.debug("build health report skipped: %s", exc)
    return "\n".join(lines)
