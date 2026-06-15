"""Owner-facing MCP + B9 quality summaries for WeChat (/简报, /委派质量)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _resolve_workspace(orchestrator: Any, session_key: str) -> Path | None:
    try:
        pm = orchestrator.project_manager
        proj = pm.get_current(session_key=str(session_key or "").strip())
        ws = getattr(proj, "workspace", None) if proj else None
        if ws:
            return Path(ws).expanduser().resolve(strict=False)
    except Exception as exc:
        logger.debug("owner quality workspace skipped: %s", exc)
    return None


def format_mcp_owner_line(
    session_key: str = "",
    *,
    workspace: Path | None = None,
) -> str:
    """One-line MCP status for /简报."""
    try:
        from butler.mcp.config import mcp_enabled, mcp_sdk_available
    except Exception:
        return "MCP: 模块不可用"

    if not mcp_enabled():
        return "MCP: 关闭（opt-in `BUTLER_MCP_ENABLED=1` + `pip install -e \".[mcp]\"`）"
    if not mcp_sdk_available():
        return "MCP: 已开启但缺 SDK（pip install butler-system[mcp]）"

    configured = 0
    try:
        from butler.registry.mcp_merge import effective_mcp_servers

        configured = len(effective_mcp_servers(workspace=workspace))
    except Exception as exc:
        logger.debug("mcp configured count skipped: %s", exc)

    connected = 0
    tools = 0
    try:
        from butler.mcp.manager import get_manager

        sk = str(session_key or "").strip() or "default"
        statuses = get_manager().status_snapshot(sk)
        connected = sum(1 for s in statuses if s.connected)
        tools = sum(int(s.tool_count or 0) for s in statuses if s.connected)
    except Exception as exc:
        logger.debug("mcp connection snapshot skipped: %s", exc)

    if configured == 0:
        return "MCP: 已开启，未配置 server（/mcp 列表）"
    if connected:
        return f"MCP: 已配置 {configured} 个 server，本会话已连接 {connected} 个（{tools} 工具）"
    return f"MCP: 已配置 {configured} 个 server，本会话未连接（/mcp 重载）"


def format_mcp_owner_block(
    session_key: str = "",
    *,
    workspace: Path | None = None,
) -> list[str]:
    """MCP subsection lines for /inbox."""
    line = format_mcp_owner_line(session_key, workspace=workspace)
    lines = ["## MCP", f"  {line}"]
    try:
        from butler.mcp.diagnostics import format_mcp_diagnostic_lines

        detail = format_mcp_diagnostic_lines(session_key)
        for row in detail[1:4]:
            lines.append(f"  {row.strip()}")
    except Exception:
        pass
    lines.append("  管理：/mcp 列表 · /mcp 安装 <id>")
    return lines


def _b9_tier_summary_from_audit(b9: dict[str, Any]) -> str:
    results = b9.get("results")
    if not isinstance(results, list) or not results:
        return ""
    try:
        from butler.dev_engine.b9_tiers import summarize_tier_results

        tiers = summarize_tier_results(results)
        t1 = tiers.get("tier1") or {}
        if not t1.get("total"):
            return ""
        rate = float(t1.get("pass_rate") or 0.0)
        return f"Tier-1 {t1.get('passed', 0)}/{t1.get('total', 0)} ({rate:.0%})"
    except Exception as exc:
        logger.debug("b9 tier summary skipped: %s", exc)
        return ""


def collect_b9_owner_snapshot() -> dict[str, Any]:
    snap: dict[str, Any] = {}
    try:
        from butler.ops.eval_diagnostics import collect_eval_quality_snapshot

        eq = collect_eval_quality_snapshot()
        if eq.b9:
            snap["b9_audit"] = dict(eq.b9)
    except Exception as exc:
        logger.debug("b9 audit snapshot skipped: %s", exc)

    try:
        from butler.ops.b9_prod_weekly import (
            compare_production_delegate_delta,
            summarize_production_delegate_quality,
        )

        snap["prod_clean"] = summarize_production_delegate_quality(clean=True)
        snap["prod_delta"] = compare_production_delegate_delta(clean=True)
    except Exception as exc:
        logger.debug("prod delegate snapshot skipped: %s", exc)
    return snap


def format_b9_owner_line() -> str:
    """One-line B9 + production delegate quality for /简报."""
    snap = collect_b9_owner_snapshot()
    parts: list[str] = []

    b9 = snap.get("b9_audit") or {}
    if b9:
        rate = float(b9.get("pass_rate") or 0.0)
        mode = str(b9.get("mode") or "oracle")
        tier = _b9_tier_summary_from_audit(b9)
        base = f"B9 {b9.get('passed', 0)}/{b9.get('total', 0)} ({rate:.0%}, {mode})"
        parts.append(f"{base} · {tier}" if tier else base)
    else:
        parts.append("B9: 未记录（bash scripts/butler-eval-llm-benchmark.sh）")

    prod = snap.get("prod_clean") or {}
    total = int(prod.get("production_failures_total") or 0)
    if total:
        top = prod.get("by_failure_reason") or {}
        lead = max(top.items(), key=lambda kv: kv[1])[0] if top else "other"
        parts.append(f"生产委派失败 {total}（主因 {lead}）")
    else:
        parts.append("生产委派失败: 0")

    delta = snap.get("prod_delta") or {}
    if int(delta.get("snapshots") or 0) >= 2:
        vf = float(delta.get("verify_fail_rate_delta") or 0.0)
        parts.append(f"周趋势 verify_fail {vf:+.0%}")
    return "委派质量: " + " · ".join(parts)


def format_delegate_quality_report() -> str:
    """WeChat /委派质量 — B9 benchmark + production taxonomy."""
    snap = collect_b9_owner_snapshot()
    lines = ["## 委派质量（B9 + 生产）", ""]

    b9 = snap.get("b9_audit") or {}
    if b9:
        rate = float(b9.get("pass_rate") or 0.0)
        mode = str(b9.get("mode") or "oracle")
        lines.append(
            f"**B9 基准**: {b9.get('passed', 0)}/{b9.get('total', 0)} "
            f"通过率 {rate:.0%}（{mode}）"
        )
        tier = _b9_tier_summary_from_audit(b9)
        if tier:
            lines.append(f"  {tier}")
        failed: list[str] = []
        for row in b9.get("results") or []:
            if not isinstance(row, dict):
                continue
            if row.get("passed"):
                continue
            tid = str(row.get("task_id") or "?")
            err = str(row.get("error") or row.get("failure") or "")[:40]
            failed.append(f"  · {tid}" + (f" — {err}" if err else ""))
        if failed:
            lines.append("  未通过:")
            lines.extend(failed[:5])
            if len(failed) > 5:
                lines.append(f"  … 另有 {len(failed) - 5} 项")
    else:
        lines.append("**B9 基准**: 尚无审计记录")
        lines.append("  运行: `bash scripts/butler-eval-llm-benchmark.sh`")

    lines.append("")
    prod = snap.get("prod_clean") or {}
    total = int(prod.get("production_failures_total") or 0)
    lines.append(f"**生产委派失败（clean）**: {total} 条")
    if total:
        for reason, count in sorted(
            (prod.get("by_failure_reason") or {}).items(),
            key=lambda kv: -int(kv[1]),
        )[:5]:
            rate = (prod.get("rates") or {}).get(reason, 0)
            lines.append(f"  · {reason}: {count} ({float(rate):.0%})")

    delta = snap.get("prod_delta") or {}
    lines.append("")
    if int(delta.get("snapshots") or 0) >= 2:
        lines.append("**周趋势（clean 快照）**:")
        for key in ("verify_fail", "patch_wrong", "no_test", "tool_wrong"):
            d = float(delta.get(f"{key}_rate_delta") or 0.0)
            lines.append(f"  · {key}: {d:+.1%}")
        dt = int(delta.get("production_failures_total_delta") or 0)
        if dt:
            lines.append(f"  · 失败总数 Δ {dt:+d}")
    else:
        note = str(delta.get("note") or "需 2+ 周快照")
        lines.append(f"**周趋势**: {note}")

    lines.append("")
    lines.append("运维: `bash scripts/butler-b9-weekly-learning.sh`")
    lines.append("详情: /诊断 -> 开发质量")
    return "\n".join(lines)


__all__ = [
    "collect_b9_owner_snapshot",
    "format_b9_owner_line",
    "format_delegate_quality_report",
    "format_mcp_owner_block",
    "format_mcp_owner_line",
]
