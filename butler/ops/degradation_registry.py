"""Process-wide degradation registry for /诊断 and butler doctor (ENG-8 / P0-B)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

from butler.ops.degradation_registry_ops import (
    append_recent_best_effort_skip_lines,
    best_effort_skip_total_safe,
    enrich_stats_with_live_mcp_safe,
    recent_compaction_acl_skip_count_safe,
    compaction_acl_counter_total_safe,
    refresh_degradations_for_owner_brief_safe,
    set_component_gauge_safe,
    sync_degradation_metrics_safe,
    sync_embedding_degradation_from_health_check_safe,
    sync_embedding_degradation_light_safe,
    sync_mcp_degradations_at_startup_safe,
)

logger = logging.getLogger(__name__)

_LOCK = threading.RLock()
_REGISTRY: dict[str, "DegradationRecord"] = {}


@dataclass(frozen=True)
class DegradationRecord:
    component: str
    reason: str
    since_ts: float
    detail: str = ""


def register_degradation(
    component: str,
    reason: str,
    *,
    detail: str = "",
) -> None:
    """Record an active degradation (idempotent per component key)."""
    key = str(component or "").strip()
    if not key:
        return
    rec = DegradationRecord(
        component=key,
        reason=str(reason or "").strip() or "degraded",
        since_ts=time.time(),
        detail=str(detail or "").strip(),
    )
    with _LOCK:
        prev = _REGISTRY.get(key)
        _REGISTRY[key] = rec
    if prev is None or prev.reason != rec.reason or prev.detail != rec.detail:
        msg = f"{key}: {rec.reason}"
        if rec.detail:
            msg = f"{msg} ({rec.detail[:120]})"
        logger.warning("Degradation active — %s", msg)
    _sync_metrics()


def clear_degradation(component: str) -> None:
    key = str(component or "").strip()
    if not key:
        return
    with _LOCK:
        removed = _REGISTRY.pop(key, None)
    if removed is not None:
        _set_component_gauge(key, active=False)
        logger.info("Degradation cleared — %s", key)
    _sync_metrics()


def list_degradations() -> list[DegradationRecord]:
    with _LOCK:
        rows = list(_REGISTRY.values())
    return sorted(rows, key=lambda r: r.since_ts)


def sync_memory_degradations_from_stats(stats: dict[str, Any]) -> None:
    """Merge memory-layer stats into the registry (called from /诊断)."""
    if not isinstance(stats, dict):
        return
    if stats.get("memory_offline"):
        err = str(stats.get("memory_init_error") or "").strip()
        register_degradation(
            "memory",
            "子系统离线",
            detail=err[:200] if err else "",
        )
    else:
        clear_degradation("memory")

    if stats.get("embedding_degraded"):
        from butler.defaults.model_defaults import DEFAULT_EMBEDDING_MODEL

        req_p = str(stats.get("embedding_requested_provider") or "?")
        req_m = str(stats.get("embedding_requested_model") or "?")
        used = str(stats.get("embedding_used_model") or DEFAULT_EMBEDDING_MODEL)
        register_degradation(
            "embedding",
            f"请求 {req_p}/{req_m} → {used}",
        )
    elif not stats.get("memory_offline"):
        clear_degradation("embedding")

    if stats.get("rag_last_recall_degraded"):
        register_degradation("recall", "hybrid 异常，仅 FTS")
    else:
        clear_degradation("recall")

    degraded_mcp = stats.get("mcp_degraded")
    if isinstance(degraded_mcp, list) and degraded_mcp:
        register_degradation("mcp", f"{len(degraded_mcp)} 个 server 不可用")
    else:
        clear_degradation("mcp")


def best_effort_skip_total() -> int:
    return best_effort_skip_total_safe()


_COMPONENT_LABELS: dict[str, str] = {
    "embedding": "嵌入",
    "recall": "检索",
    "memory": "记忆",
    "mcp": "MCP",
    "skills": "Skill",
    "compaction_acl": "压缩ACL",
}


def _format_since_ts(since_ts: float) -> str:
    age_s = max(0, int(time.time() - float(since_ts or 0)))
    if age_s < 60:
        return f"{age_s}s"
    if age_s < 3600:
        return f"{age_s // 60}m"
    return f"{age_s // 3600}h"


def format_brief_line() -> str | None:
    """One Owner line: ``降级：… N 项（…）→ /诊断 详细``."""
    rows = list_degradations()
    if not rows:
        return None
    labels = [_COMPONENT_LABELS.get(r.component, r.component) for r in rows[:4]]
    suffix = f" 等{len(rows)}项" if len(rows) > 4 else ""
    return (
        f"降级：{len(rows)} 项（{' · '.join(labels)}{suffix}）"
        " → /诊断 详细"
    )


def format_diagnostic_lines() -> list[str]:
    rows = list_degradations()
    skip_n = best_effort_skip_total()
    if not rows and skip_n <= 0:
        return []
    lines = ["运行降级:"]
    for rec in rows:
        since = _format_since_ts(rec.since_ts)
        line = f"  - {rec.component}: {rec.reason} (持续 {since})"
        if rec.detail:
            line += f" — {rec.detail[:120]}"
        lines.append(line)
    if skip_n > 0:
        lines.append(f"  可选路径跳过: {skip_n} 次 (best_effort_skip)")
    append_recent_best_effort_skip_lines(lines)
    return lines


def sync_embedding_degradation_light() -> None:
    """Fast embedder probe for gateway warm-up (no Recall@K index)."""
    sync_embedding_degradation_light_safe()


def sync_embedding_degradation_from_health_check(*, min_recall: float = 0.5) -> None:
    """Full Recall@K probe for ``butler doctor`` / release checks."""
    sync_embedding_degradation_from_health_check_safe(min_recall=min_recall)


def sync_compaction_acl_from_metrics() -> None:
    """Register compaction ACL degradations from runtime counters / recent skips."""
    total = compaction_acl_counter_total_safe()
    if total <= 0:
        total = recent_compaction_acl_skip_count_safe()
    if total > 0:
        register_degradation("compaction_acl", f"累计降级 {total} 次")
    else:
        clear_degradation("compaction_acl")


def sync_all_startup_degradations(*, session_key: str = "gateway:warmup") -> None:
    """Gateway warm-up: MCP + embedding light probe + compaction ACL metrics."""
    sync_mcp_degradations_at_startup(session_key=session_key)
    sync_embedding_degradation_light()
    sync_compaction_acl_from_metrics()


def sync_mcp_degradations_at_startup(*, session_key: str = "gateway:warmup") -> None:
    """Probe MCP at gateway warm-up; register active degradations (ENG-8 续)."""
    sync_mcp_degradations_at_startup_safe(session_key=session_key)


def enrich_stats_with_live_mcp(
    stats: dict[str, Any],
    *,
    session_key: str = "",
) -> dict[str, Any]:
    """Attach live MCP snapshot for owner brief / diagnostic sync (ENG-8)."""
    return enrich_stats_with_live_mcp_safe(stats, session_key=session_key)


def refresh_degradations_for_owner_brief(
    orchestrator: Any,
    *,
    session_key: str = "",
    health: dict[str, Any] | None = None,
) -> str | None:
    """Sync memory + MCP into registry; return one brief line for Owner /诊断."""
    return refresh_degradations_for_owner_brief_safe(
        orchestrator,
        session_key=session_key,
        health=health,
    )


def _set_component_gauge(component: str, *, active: bool) -> None:
    set_component_gauge_safe(component, active=active)


def _sync_metrics() -> None:
    with _LOCK:
        registry_snapshot = dict(_REGISTRY)
    sync_degradation_metrics_safe(registry_snapshot)


__all__ = [
    "DegradationRecord",
    "best_effort_skip_total",
    "clear_degradation",
    "enrich_stats_with_live_mcp",
    "format_brief_line",
    "format_diagnostic_lines",
    "list_degradations",
    "refresh_degradations_for_owner_brief",
    "register_degradation",
    "sync_all_startup_degradations",
    "sync_compaction_acl_from_metrics",
    "sync_embedding_degradation_from_health_check",
    "sync_embedding_degradation_light",
    "sync_mcp_degradations_at_startup",
    "sync_memory_degradations_from_stats",
]
