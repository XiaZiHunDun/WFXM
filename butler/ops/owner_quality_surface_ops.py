"""Owner-facing MCP + B9 quality best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.mcp.config import mcp_enabled, mcp_sdk_available
from butler.registry.mcp_merge import effective_mcp_servers
from butler.mcp.manager import get_manager
from butler.mcp.diagnostics import format_mcp_diagnostic_lines
from butler.dev_engine.b9_tiers import summarize_tier_results
from butler.ops.eval_diagnostics import collect_eval_quality_snapshot
from butler.ops.b9_prod_weekly import compare_production_delegate_delta, summarize_production_delegate_quality
from butler.config import get_butler_home

logger = logging.getLogger(__name__)


def resolve_workspace_safe(orchestrator: Any, session_key: str) -> Path | None:
    def _run() -> Path | None:
        pm = orchestrator.project_manager
        proj = pm.get_current(session_key=str(session_key or "").strip())
        ws = getattr(proj, "workspace", None) if proj else None
        if ws:
            return Path(ws).expanduser().resolve(strict=False)
        return None

    result = safe_best_effort(
        _run,
        label="owner_quality.workspace",
        default=None,
    )
    return result if isinstance(result, Path) else None


def mcp_import_available() -> bool:
    def _run() -> bool:

        return True

    return safe_best_effort(_run, label="owner_quality.mcp_import", default=False) is True


def mcp_configured_count(workspace: Path | None) -> int:
    def _run() -> int:

        return len(effective_mcp_servers(workspace=workspace))

    result = safe_best_effort(_run, label="owner_quality.mcp_configured", default=0)
    return int(result) if isinstance(result, int) else 0


def mcp_connection_snapshot(session_key: str) -> tuple[int, int]:
    def _run() -> tuple[int, int]:

        sk = str(session_key or "").strip() or "default"
        statuses = get_manager().status_snapshot(sk)
        connected = sum(1 for s in statuses if s.connected)
        tools = sum(int(s.tool_count or 0) for s in statuses if s.connected)
        return connected, tools

    result = safe_best_effort(
        _run,
        label="owner_quality.mcp_snapshot",
        default=(0, 0),
    )
    if isinstance(result, tuple) and len(result) == 2:
        return int(result[0]), int(result[1])
    return 0, 0


def mcp_diagnostic_detail_lines(session_key: str) -> list[str]:
    def _run() -> list[str]:

        return list(format_mcp_diagnostic_lines(session_key))

    result = safe_best_effort(
        _run,
        label="owner_quality.mcp_diagnostics",
        default=[],
    )
    return result if isinstance(result, list) else []


def b9_tier_summary_safe(b9: dict[str, Any]) -> str:
    results = b9.get("results")
    if not isinstance(results, list) or not results:
        return ""

    def _run() -> str:

        tiers = summarize_tier_results(results)
        t1 = tiers.get("tier1") or {}
        if not t1.get("total"):
            return ""
        rate = float(t1.get("pass_rate") or 0.0)
        return f"Tier-1 {t1.get('passed', 0)}/{t1.get('total', 0)} ({rate:.0%})"

    result = safe_best_effort(_run, label="owner_quality.b9_tier", default="")
    return result if isinstance(result, str) else ""


def b9_audit_snapshot_safe() -> dict[str, Any] | None:
    def _run() -> dict[str, Any] | None:

        eq = collect_eval_quality_snapshot()
        if eq.b9:
            return dict(eq.b9)
        return None

    result = safe_best_effort(_run, label="owner_quality.b9_audit", default=None)
    return result if result is None or isinstance(result, dict) else None


def prod_delegate_snapshots_safe() -> tuple[dict[str, Any], dict[str, Any]]:
    def _run() -> tuple[dict[str, Any], dict[str, Any]]:

        return (
            summarize_production_delegate_quality(clean=True),
            compare_production_delegate_delta(clean=True),
        )

    result = safe_best_effort(
        _run,
        label="owner_quality.prod_delegate",
        default=({}, {}),
    )
    if isinstance(result, tuple) and len(result) == 2:
        clean, delta = result
        return (
            dict(clean) if isinstance(clean, dict) else {},
            dict(delta) if isinstance(delta, dict) else {},
        )
    return {}, {}


def review_candidates_count_safe() -> int:
    def _run() -> int:

        pending = get_butler_home() / "experiences" / "review_candidates.jsonl"
        if pending.is_file():
            return sum(1 for _ in pending.open(encoding="utf-8"))
        return 0

    result = safe_best_effort(
        _run,
        label="owner_quality.review_candidates",
        default=0,
    )
    return int(result) if isinstance(result, int) else 0
