"""Execution surface diagnostics for /诊断 and ``butler doctor`` (Skill · Tool · MCP)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def legacy_global_skills_dir(butler_home: Path) -> Path:
    return Path(butler_home).expanduser().resolve() / "skills"


def check_legacy_global_skills(butler_home: Path) -> list[str]:
    """Warn when pre-tenant ``~/.butler/skills/`` still has files alongside tenant dir."""
    home = Path(butler_home).expanduser().resolve()
    legacy = legacy_global_skills_dir(home)
    if not legacy.is_dir():
        return []
    md_files = sorted(legacy.glob("*.md"))
    if not md_files:
        return []
    from butler.tenant import DEFAULT_TENANT, tenant_skills_dir

    tenant_dir = tenant_skills_dir(home, DEFAULT_TENANT)
    names = ", ".join(p.name for p in md_files[:5])
    if len(md_files) > 5:
        names += " …"
    return [
        f"遗留全局 Skill 目录仍有 {len(md_files)} 个文件 ({names})",
        f"  路径: {legacy}",
        f"  建议: 合并到 {tenant_dir} 后删除遗留目录（runtime 不读此路径）",
    ]


def project_skills_sync_issues(workspace: Path) -> list[str]:
    """Detect git ``skills/`` vs runtime ``.butler/skills/`` drift."""
    from butler.skills.layout import project_skills_sync_issues as _layout_issues

    return _layout_issues(workspace)


def collect_execution_surface_stats(
    orchestrator: Any,
    *,
    health: dict[str, Any] | None = None,
    session_key: str = "",
) -> dict[str, Any]:
    """Aggregate Skill/Tool/MCP snapshot for diagnostics."""
    h = health or {}
    loop = h.get("loop") if isinstance(h.get("loop"), dict) else {}

    def _pick(*keys: str) -> Any:
        for key in keys:
            if key in h and h.get(key) is not None:
                return h.get(key)
            if key in loop and loop.get(key) is not None:
                return loop.get(key)
        return None

    stats: dict[str, Any] = {}
    try:
        from butler.skills.injection_policy import skill_injection_mode

        stats["skill_injection_mode"] = skill_injection_mode()
    except Exception as exc:
        logger.debug("skill injection mode skipped: %s", exc)

    for key in (
        "skill_injection_reason",
        "skill_injection_experience_hits",
        "skill_injection_refs",
        "skill_context_injected",
        "skill_matches",
        "experience_pinned_tools",
        "experience_mcp_promoted",
        "tool_selector_input",
        "tool_selector_output",
        "tool_selector_dropped",
    ):
        val = _pick(key)
        if val is not None:
            stats[key] = val

    try:
        orch = orchestrator
        mgr = getattr(orch, "_skill_manager", None)
        if mgr is not None:
            stats["skill_catalog_count"] = len(mgr.list_skills())
    except Exception as exc:
        logger.debug("skill catalog count skipped: %s", exc)

    try:
        from butler.core.harness_flags import mcp_deferred_tools_enabled
        from butler.mcp.config import mcp_enabled

        stats["mcp_enabled"] = mcp_enabled()
        stats["mcp_deferred"] = mcp_deferred_tools_enabled()
        if mcp_enabled() and mcp_deferred_tools_enabled():
            from butler.mcp.deferred import get_promoted_tools

            sk = str(session_key or h.get("session_key") or "").strip()
            promoted = sorted(get_promoted_tools(sk))
            stats["mcp_promoted_tools"] = promoted
    except Exception as exc:
        logger.debug("mcp promoted tools skipped: %s", exc)

    try:
        from butler.config import get_butler_home

        stats["legacy_skill_warnings"] = check_legacy_global_skills(get_butler_home())
    except Exception as exc:
        logger.debug("legacy skills check skipped: %s", exc)

    proj = None
    try:
        pm = getattr(orchestrator, "project_manager", None)
        if pm is not None:
            proj = pm.get_current(session_key=session_key or None)
    except Exception:
        proj = None
    if proj is not None and getattr(proj, "workspace", None):
        stats["skills_sync_issues"] = project_skills_sync_issues(Path(proj.workspace))

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

    try:
        from butler.mcp.diagnostics import format_mcp_diagnostic_lines

        mcp_lines = format_mcp_diagnostic_lines(session_key)
        if mcp_lines:
            lines.append("  --- MCP 连接 ---")
            for ml in mcp_lines[:8]:
                lines.append(f"  {ml}" if not ml.startswith(" ") else ml)
    except Exception as exc:
        logger.debug("mcp diagnostic embed skipped: %s", exc)

    return lines


__all__ = [
    "check_legacy_global_skills",
    "collect_execution_surface_stats",
    "format_execution_surface_diagnostic_lines",
    "legacy_global_skills_dir",
    "project_skills_sync_issues",
]
