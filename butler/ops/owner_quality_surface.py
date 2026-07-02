"""Owner-facing MCP + B9 quality summaries for WeChat (/简报, /委派质量)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from butler.ops.owner_quality_surface_ops import (
    b9_audit_snapshot_safe,
    b9_tier_summary_safe,
    mcp_configured_count,
    mcp_connection_snapshot,
    mcp_diagnostic_detail_lines,
    mcp_import_available,
    prod_delegate_snapshots_safe,
    resolve_workspace_safe,
    review_candidates_count_safe,
)


def _resolve_workspace(orchestrator: Any, session_key: str) -> Path | None:
    return resolve_workspace_safe(orchestrator, session_key)


def format_mcp_owner_line(
    session_key: str = "",
    *,
    workspace: Path | None = None,
) -> str:
    """One-line MCP status for /简报."""
    if not mcp_import_available():
        return "MCP: 模块不可用"

    from butler.mcp.config import mcp_enabled, mcp_sdk_available

    if not mcp_enabled():
        return "MCP: 关闭（opt-in `BUTLER_MCP_ENABLED=1` + `pip install -e \".[mcp]\"`）"
    if not mcp_sdk_available():
        return "MCP: 已开启但缺 SDK（pip install butler-system[mcp]）"

    configured = mcp_configured_count(workspace)
    connected, tools = mcp_connection_snapshot(session_key)

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
    detail = mcp_diagnostic_detail_lines(session_key)
    for row in detail[1:4]:
        lines.append(f"  {row.strip()}")
    lines.append("  管理：/mcp 列表 · /mcp 安装 <id>")
    return lines


def _b9_tier_summary_from_audit(b9: dict[str, Any]) -> str:
    return b9_tier_summary_safe(b9)


def collect_b9_owner_snapshot() -> dict[str, Any]:
    snap: dict[str, Any] = {}
    b9 = b9_audit_snapshot_safe()
    if b9:
        snap["b9_audit"] = b9
    prod_clean, prod_delta = prod_delegate_snapshots_safe()
    if prod_clean:
        snap["prod_clean"] = prod_clean
    if prod_delta:
        snap["prod_delta"] = prod_delta
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
    count = review_candidates_count_safe()
    if count:
        lines.append(f"**审查经验候选**: {count} 条（`review_candidates.jsonl`）")
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
