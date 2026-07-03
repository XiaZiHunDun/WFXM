"""WS-H owner trust surface — permissions, injection policy, boundaries."""

from __future__ import annotations

from typing import Any

from butler.ops.owner_trust_surface_ops import (
    approval_stats_for_health_safe,
    boundary_warn_count_safe,
    execution_trust_session_safe,
    memory_sources_line_safe,
    skill_injection_mode_safe,
)


def collect_trust_snapshot(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict[str, Any] | None = None,
) -> dict[str, Any]:
    sk = str(session_key or "").strip()
    h = dict(health or {})
    snap: dict[str, Any] = {}

    mode = skill_injection_mode_safe()
    if mode:
        snap["skill_mode"] = mode

    loop = h.get("loop")
    if isinstance(loop, dict):
        for key in ("skill_injection_reason", "skill_injection_experience_hits"):
            if key in loop:
                snap[key] = loop[key]
    for key in ("skill_injection_reason", "skill_injection_experience_hits"):
        if key in h:
            snap[key] = h[key]

    snap["approvals"] = approval_stats_for_health_safe(sk)
    snap["boundary_warns"] = boundary_warn_count_safe()
    snap["execution_trust"] = execution_trust_session_safe(sk)
    snap["memory_line"] = memory_sources_line_safe(h)

    return snap


def format_trust_owner_line(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict[str, Any] | None = None,
) -> str:
    snap = collect_trust_snapshot(orchestrator, session_key, health=health)
    parts: list[str] = []

    mode = snap.get("skill_mode")
    if mode:
        reason = snap.get("skill_injection_reason")
        bit = f"Skill:{mode}"
        if reason:
            bit += f"/{reason}"
        parts.append(bit)

    approvals = snap.get("approvals") or {}
    if approvals.get("has_pending"):
        parts.append("权限待批")
    once = int(approvals.get("once_active_count") or 0)
    if once:
        parts.append(f"本次允许{once}项")

    warns = int(snap.get("boundary_warns") or 0)
    if warns:
        parts.append(f"边界warn{warns}")

    trust = snap.get("execution_trust") or {}
    trust_total = sum(int(v) for v in trust.values())
    if trust_total:
        parts.append(f"信任级联{trust_total}")

    mem = str(snap.get("memory_line") or "").strip()
    if mem and mem.startswith("记忆来源:"):
        parts.append(mem.replace("记忆来源: ", "记忆:", 1))

    if not parts:
        return "信任: 正常（经验优先 / Skill 兜底）"
    return "信任: " + " · ".join(parts)


def format_trust_owner_block(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict[str, Any] | None = None,
) -> list[str]:
    line = format_trust_owner_line(orchestrator, session_key, health=health)
    return ["## 信任", f"  {line}", "  详情：/信任 · /记忆来源"]


def format_trust_report(
    orchestrator: Any,
    session_key: str,
    *,
    health: dict[str, Any] | None = None,
) -> str:
    snap = collect_trust_snapshot(orchestrator, session_key, health=health)
    lines = ["🛡️ 信任与透明度", ""]

    mode = snap.get("skill_mode") or "fallback"
    lines.append(f"Skill 注入模式: {mode} (`BUTLER_SKILL_INJECTION_MODE`)")
    reason = snap.get("skill_injection_reason")
    if reason:
        lines.append(f"  上轮原因: {reason}")
    n_exp = snap.get("skill_injection_experience_hits")
    if n_exp is not None:
        lines.append(f"  上轮经验命中(策略): {n_exp}")

    lines.append("")
    approvals = snap.get("approvals") or {}
    lines.append("权限批准缓存:")
    lines.append(
        f"  始终允许 {int(approvals.get('always_count') or 0)} 项 · "
        f"本次允许 {int(approvals.get('once_active_count') or 0)} 项"
    )
    if approvals.get("has_pending"):
        lines.append("  ⏳ 有 1 项待批准（/批准一次）")

    lines.append("")
    trust = snap.get("execution_trust") or {}
    if trust:
        lines.append("本会话信任级联计数:")
        for name, count in sorted(trust.items()):
            lines.append(f"  · {name}: {count}")
    else:
        lines.append("本会话信任级联: 暂无计数")

    warns = int(snap.get("boundary_warns") or 0)
    lines.append("")
    lines.append(f"诚实边界观测: {warns} 项 warn（/诊断 可看 G1/G2）")

    mem = str(snap.get("memory_line") or "").strip()
    lines.append("")
    if mem:
        lines.append(mem)
    else:
        lines.append("记忆来源: 尚无上轮记录")

    lines.append("")
    lines.append("说明: 经验优先、Skill 未验证兜底；回忆清单会跳过预取。")
    lines.append("纠正: 发送「刚才那句不对：…」自动写入 correction 经验。")
    lines.append("详情: /记忆来源 · /压缩报告 · /诊断")
    return "\n".join(lines)


__all__ = [
    "collect_trust_snapshot",
    "format_trust_owner_block",
    "format_trust_owner_line",
    "format_trust_report",
]
