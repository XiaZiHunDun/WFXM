"""Process-wide degradation registry for /诊断 and butler doctor (ENG-8 / P0-B)."""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any

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
        _REGISTRY[key] = rec
    _sync_metrics()


def clear_degradation(component: str) -> None:
    key = str(component or "").strip()
    if not key:
        return
    with _LOCK:
        _REGISTRY.pop(key, None)
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
        req_p = str(stats.get("embedding_requested_provider") or "?")
        req_m = str(stats.get("embedding_requested_model") or "?")
        used = str(stats.get("embedding_used_model") or "hashing-v1")
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
    try:
        from butler.ops.runtime_metrics import snapshot_global

        snap = snapshot_global()
        counters = snap.get("counters") if isinstance(snap, dict) else None
        if not isinstance(counters, dict):
            return 0
        return sum(
            int(value or 0)
            for key, value in counters.items()
            if str(key).startswith("best_effort_skip")
        )
    except Exception:
        return 0


_COMPONENT_LABELS: dict[str, str] = {
    "embedding": "嵌入",
    "recall": "检索",
    "memory": "记忆",
    "mcp": "MCP",
    "skills": "Skill",
}


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
        line = f"  - {rec.component}: {rec.reason}"
        if rec.detail:
            line += f" ({rec.detail[:120]})"
        lines.append(line)
    if skip_n > 0:
        lines.append(f"  可选路径跳过: {skip_n} 次 (best_effort_skip)")
    try:
        from butler.core.best_effort import recent_best_effort_skips

        recent = recent_best_effort_skips(5)
        for _ts, path, err in recent:
            lines.append(f"    · {path}: {err[:100]}")
    except Exception:
        pass
    return lines


def _sync_metrics() -> None:
    try:
        from butler.ops.runtime_metrics import set_gauge

        with _LOCK:
            n = len(_REGISTRY)
        set_gauge("degradation_active", float(n))
    except Exception as exc:
        logger.debug("degradation metrics sync skipped: %s", exc)


__all__ = [
    "DegradationRecord",
    "best_effort_skip_total",
    "clear_degradation",
    "format_brief_line",
    "format_diagnostic_lines",
    "list_degradations",
    "register_degradation",
    "sync_memory_degradations_from_stats",
]
