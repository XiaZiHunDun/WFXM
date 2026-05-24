"""Build ``/health`` and ``/诊断`` text from orchestrator + session snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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


def _shared_diagnostic_lines(
    inp: HealthReportInput,
    *,
    use_mem_stats_project_name: bool = False,
) -> list[str]:
    from butler.memory.diagnostics import format_memory_diagnostic_lines
    from butler.model_resolve import format_model_diagnostic_lines
    from butler.ops.snapshot import format_ops_diagnostic_lines
    from butler.project_meta import format_project_meta_lines
    from butler.runtime.diagnostics import format_runtime_diagnostic_lines

    lines: list[str] = []
    lines.extend(format_memory_diagnostic_lines(inp.mem_stats))
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

    from butler.project_lead import lead_mode_banner_line

    agent_role = str(health.get("gateway_agent_role") or "butler")
    engine_line = (
        lead_mode_banner_line()
        if agent_role == "lead"
        else "对话引擎: 管家 Butler"
    )
    from butler.core.context_budget import format_context_budget_line

    context_line = format_context_budget_line(health)
    compact_note = "否"
    if health.get("hygiene_compressed"):
        compact_note = "是"
    elif health.get("context_compact_circuit_open"):
        compact_note = "熔断跳过"
    elif health.get("hygiene_compact_skipped"):
        compact_note = f"跳过({health.get('hygiene_compact_skipped')})"

    return [
        "Butler 诊断",
        f"会话: {health.get('session_key') or inp.session_key}",
        f"平台: {health.get('platform') or '-'}",
        engine_line,
        context_line,
        f"记忆提炼模型(post_session): {aux_label}",
        f"压缩: {compact_note}",
        f"Schema 降级: {'是' if schema_recovered else '否'}",
        f"剥离关键字: {schema_keywords}",
        f"Skill: {'已注入' if health.get('skill_context_injected') else '未注入'}",
        f"命中 Skill: {', '.join(str(s) for s in skill_matches) if skill_matches else '-'}",
        f"记忆上下文: {'已注入' if health.get('memory_context_injected') else '未注入'}",
        f"记忆同步: {'已同步' if not memory_sync.get('skipped', True) else '跳过'}",
        f"Provider 同步: {'是' if memory_sync.get('provider_synced') else '否'}",
    ]


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
        lines = [
            "Butler 诊断",
            f"会话: {inp.session_key}",
            "轮次诊断: 暂无（本会话尚无完整对话轮次）",
        ]
        lines.extend(_shared_diagnostic_lines(inp))
        return "\n".join(lines)

    lines: list[str] = []
    if health:
        lines.extend(_turn_diagnostic_lines(inp))
        lines.extend(_shared_diagnostic_lines(inp, use_mem_stats_project_name=True))
        if health.get("error"):
            lines.append("错误: 有（查看日志）")
        if health.get("hygiene_error"):
            lines.append("压缩错误: 有（查看日志）")
    else:
        lines = [
            "Butler 诊断",
            f"会话: {inp.session_key}",
            "轮次诊断: 暂无（本会话尚无完整对话轮次）",
        ]
        lines.extend(_shared_diagnostic_lines(inp))

    lines.extend(_tool_audit_lines(tool_summary))
    return "\n".join(lines)
