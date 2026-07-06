"""Execution surface diagnostics for /诊断 and ``butler doctor`` (Skill · Tool · MCP)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from butler.ops.execution_surface_collect import (
    check_legacy_global_skills,
    collect_digestion_health,
    collect_execution_trust_metrics,
    current_project,
    default_mcp_config_path as _default_mcp_config_path,
    legacy_global_skills_dir,
    legacy_skill_warnings,
    mcp_diagnostic_lines,
    mcp_enabled_flag,
    mcp_imports_available,
    mcp_surface_flags,
    skill_catalog_count,
    skill_injection_mode,
)

_MCP_REJECT_REASON_HINTS: dict[str, str] = {
    "mcp_disabled": "MCP 未启用或未配置（BUTLER_MCP_ENABLED=1 + mcp.yaml）",
    "tool_not_found": "工具未连接或不在 catalog",
    "connect_failed": "MCP 连接失败",
    "invalid_registered_name": "MCP 注册名无效",
}


def mcp_degraded_hints(*, mcp_rejected: list[dict[str, str]] | None = None) -> list[str]:
    """Actionable hints when MCP is off or experience promote failed."""
    hints: list[str] = []
    if not mcp_imports_available():
        return hints

    if mcp_enabled_flag():
        return hints

    config_path = _default_mcp_config_path()
    if config_path is None or not config_path.is_file():
        from butler.registry.paths import default_mcp_config_path

        config_path = default_mcp_config_path()
    if not config_path.is_file():
        hints.append(
            f"未找到 MCP 配置 ({config_path})；经验 mcp: 指针不会 promote"
        )
    else:
        hints.append(
            "MCP 配置存在但 BUTLER_MCP_ENABLED 未开；经验 mcp: 指针不会 promote"
        )

    for item in mcp_rejected or []:
        reason = str(item.get("reason") or "").strip()
        name = str(item.get("name") or "").strip()
        if reason == "mcp_disabled" and name:
            detail = _MCP_REJECT_REASON_HINTS.get(reason, reason)
            hints.append(f"上轮拒绝 {name}: {detail}")
            break

    return hints


def project_skills_sync_issues(workspace: Path) -> list[str]:
    """Detect git ``skills/`` vs runtime ``.butler/skills/`` drift."""
    from butler.skills.layout import project_skills_sync_issues as _layout_issues

    return cast(list[str], _layout_issues(workspace))


def collect_execution_surface_stats(
    orchestrator: Any,
    *,
    health: dict[str, Any] | None = None,
    session_key: str = "",
) -> dict[str, Any]:
    """Aggregate Skill/Tool/MCP snapshot for diagnostics."""
    h = health or {}
    loop_raw = h.get("loop")
    loop: dict[str, Any] = loop_raw if isinstance(loop_raw, dict) else {}

    def _pick(*keys: str) -> Any:
        for key in keys:
            if key in h and h.get(key) is not None:
                return h.get(key)
            if key in loop and loop.get(key) is not None:
                return loop.get(key)
        return None

    stats: dict[str, Any] = {}
    mode = skill_injection_mode()
    if mode:
        stats["skill_injection_mode"] = mode

    for key in (
        "skill_injection_reason",
        "skill_injection_experience_hits",
        "skill_injection_refs",
        "skill_context_injected",
        "skill_matches",
        "experience_pinned_tools",
        "experience_mcp_promoted",
        "experience_mcp_rejected",
        "experience_mcp_same_turn",
        "tool_selector_input",
        "tool_selector_output",
        "tool_selector_dropped",
    ):
        val = _pick(key)
        if val is not None:
            stats[key] = val

    cat_n = skill_catalog_count(orchestrator)
    if cat_n is not None:
        stats["skill_catalog_count"] = cat_n

    stats.update(
        mcp_surface_flags(
            session_key=session_key,
            health_session_key=str(h.get("session_key") or ""),
        )
    )

    legacy = legacy_skill_warnings()
    if legacy:
        stats["legacy_skill_warnings"] = legacy

    proj = current_project(orchestrator, session_key=session_key)
    if proj is not None and getattr(proj, "workspace", None):
        stats["skills_sync_issues"] = project_skills_sync_issues(Path(proj.workspace))

    trust_metrics = collect_execution_trust_metrics(session_key=session_key)
    if trust_metrics:
        stats["execution_trust_metrics"] = trust_metrics

    digestion = collect_digestion_health()
    if digestion:
        stats["digestion_health"] = digestion

    rejected = stats.get("experience_mcp_rejected")
    if isinstance(rejected, list):
        hints = mcp_degraded_hints(mcp_rejected=rejected)
        if hints:
            stats["mcp_degraded_hints"] = hints
    elif not stats.get("mcp_enabled"):
        hints = mcp_degraded_hints()
        if hints:
            stats["mcp_degraded_hints"] = hints

    return stats


def format_execution_surface_diagnostic_lines(
    stats: dict[str, Any] | None,
    *,
    session_key: str = "",
) -> list[str]:
    """Human-readable execution surface block for /诊断."""
    if not stats:
        return []

    lines: list[str] = ["执行面 (Skill · Tool · MCP):"]

    mode = stats.get("skill_injection_mode")
    if mode:
        lines.append(f"  Skill 注入模式: {mode}")
    reason = stats.get("skill_injection_reason")
    if reason:
        lines.append(f"  上轮注入原因: {reason}")
    n_exp = stats.get("skill_injection_experience_hits")
    if n_exp is not None:
        lines.append(f"  经验命中(策略): {n_exp}")
    refs = stats.get("skill_injection_refs")
    if refs:
        if isinstance(refs, list):
            lines.append(f"  经验 skill: 指针: {', '.join(str(r) for r in refs)}")
        else:
            lines.append(f"  经验 skill: 指针: {refs}")

    cat_n = stats.get("skill_catalog_count")
    if cat_n is not None:
        lines.append(f"  Skill 目录: {cat_n} 个（租户+项目）")

    pinned = stats.get("experience_pinned_tools")
    if pinned is not None:
        lines.append(f"  经验/Skill pin 工具数: {pinned}")
    sel_in = stats.get("tool_selector_input")
    sel_out = stats.get("tool_selector_output")
    if sel_out is not None:
        dropped = int(stats.get("tool_selector_dropped") or 0)
        if sel_in is not None:
            lines.append(f"  工具预选: {sel_out}/{sel_in} (省略 {dropped})")
        else:
            lines.append(f"  工具预选出站: {sel_out} (省略 {dropped})")

    mcp_on = stats.get("mcp_enabled")
    if mcp_on is not None:
        deferred = stats.get("mcp_deferred")
        lines.append(
            f"  MCP: {'开' if mcp_on else '关'}"
            + (f", deferred={'是' if deferred else '否'}" if mcp_on else "")
        )
        promoted = stats.get("mcp_promoted_tools")
        if promoted is not None:
            if promoted:
                shown = ", ".join(str(n) for n in promoted[:6])
                if len(promoted) > 6:
                    shown += " …"
                lines.append(f"  MCP 已 promote: {shown}")
            elif stats.get("mcp_deferred"):
                lines.append("  MCP 已 promote: （无）")
        mcp_promoted_turn = stats.get("experience_mcp_promoted")
        if mcp_promoted_turn:
            lines.append(f"  上轮经验 mcp: promote: {mcp_promoted_turn}")
        same_turn = stats.get("experience_mcp_same_turn")
        if same_turn:
            lines.append(f"  上轮经验 mcp: 同轮 schema: {same_turn}")
        rejected = stats.get("experience_mcp_rejected")
        if isinstance(rejected, list) and rejected:
            for item in rejected[:4]:
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or "?").strip()
                reason = str(item.get("reason") or "unknown").strip()
                hint = _MCP_REJECT_REASON_HINTS.get(reason, reason)
                lines.append(f"  上轮经验 mcp: 拒绝 {name}: {hint}")
            if len(rejected) > 4:
                lines.append(f"  … 另有 {len(rejected) - 4} 条 mcp 拒绝")
        if stats.get("mcp_deferred_same_turn"):
            lines.append("  MCP 同轮: BUTLER_MCP_DEFERRED_SAME_TURN=1")
        elif mcp_on and stats.get("mcp_deferred"):
            lines.append("  MCP 同轮: 关（promote 后默认下一轮可见 schema）")

    for hint in stats.get("mcp_degraded_hints") or []:
        lines.append(f"  ⚠ {hint}")

    trust = stats.get("execution_trust_metrics") or {}
    if trust:
        lines.append("  信任级联计数(进程):")
        if trust.get("execution_fallback_skip"):
            lines.append(f"    fallback_skip: {trust['execution_fallback_skip']}")
        if trust.get("execution_ref_only_load"):
            lines.append(f"    ref_only_load: {trust['execution_ref_only_load']}")
        pin_total = trust.get("execution_pointer_pin")
        if pin_total:
            lines.append(f"    pointer_pin: {pin_total}")
        by_source = trust.get("execution_pointer_pin_by_source") or {}
        for source, count in sorted(by_source.items()):
            lines.append(f"      · {source}: {count}")
        sess = trust.get("session")
        if isinstance(sess, dict) and sess:
            parts = [f"{k}={v}" for k, v in sorted(sess.items())]
            lines.append(f"    本会话: {', '.join(parts)}")

    digestion = stats.get("digestion_health") or {}
    if digestion:
        lines.append("  消化健康度:")
        n_tools = digestion.get("builtin_tool_count")
        if n_tools is not None:
            lines.append(f"    builtin 工具注册: {n_tools}")
        for key, label in (
            ("digestion_skill_fallback_merge", "Skill 合并降级"),
            ("digestion_experience_merged", "经验自动合并"),
            ("digestion_experience_merge_pending", "经验合并入队"),
        ):
            if key in digestion:
                lines.append(f"    {label}: {digestion[key]}")
        pend = digestion.get("experience_merge_pending")
        if pend:
            lines.append(f"    经验合并待审: {pend} 条")
        for warn in digestion.get("tool_orthogonality_warnings") or []:
            lines.append(f"    ⚠ 工具重叠: {warn}")

    sync_issues = stats.get("skills_sync_issues") or []
    if sync_issues:
        lines.append("  项目 Skill 同步:")
        lines.extend(sync_issues[:6])

    for warn in stats.get("legacy_skill_warnings") or []:
        text = str(warn).strip()
        if text.startswith("路径:") or text.startswith("建议:"):
            lines.append(f"  {text}")
        else:
            lines.append(f"  ⚠ {text}")

    if len(lines) == 1:
        return []

    mcp_lines = mcp_diagnostic_lines(session_key)
    if mcp_lines:
        lines.append("  --- MCP 连接 ---")
        for ml in mcp_lines[:8]:
            lines.append(f"  {ml}" if not ml.startswith(" ") else ml)

    return lines


__all__ = [
    "check_legacy_global_skills",
    "collect_digestion_health",
    "collect_execution_surface_stats",
    "collect_execution_trust_metrics",
    "format_execution_surface_diagnostic_lines",
    "legacy_global_skills_dir",
    "mcp_degraded_hints",
    "project_skills_sync_issues",
]
