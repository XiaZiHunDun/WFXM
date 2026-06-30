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
    try:
        from butler.core.best_effort import recent_best_effort_skips

        recent = recent_best_effort_skips(5)
        for _ts, path, err in recent:
            lines.append(f"    · {path}: {err[:100]}")
    except Exception:
        pass
    return lines


def sync_embedding_degradation_light() -> None:
    """Fast embedder probe for gateway warm-up (no Recall@K index)."""
    try:
        from butler.memory.embedding import HashingEmbedder, get_embedder
        from butler.memory.semantic_config import embedding_model_name, embedding_provider_name

        embedder = get_embedder()
        provider = embedding_provider_name()
        model = embedding_model_name()
        if isinstance(embedder, HashingEmbedder) and provider not in ("local", ""):
            register_degradation(
                "embedding",
                f"请求 {provider}/{model} → hashing fallback",
            )
        else:
            clear_degradation("embedding")
    except Exception as exc:
        logger.debug("embedding light degradation sync skipped: %s", exc)


def sync_embedding_degradation_from_health_check(*, min_recall: float = 0.5) -> None:
    """Full Recall@K probe for ``butler doctor`` / release checks."""
    try:
        from butler.ops.embedding_health import check_embedding_recall

        report = check_embedding_recall(min_recall=min_recall)
        if report.degraded:
            register_degradation("embedding", report.message[:200])
        elif not report.ok(min_recall=min_recall):
            register_degradation("embedding", f"Recall@3 偏低: {report.message[:160]}")
        else:
            clear_degradation("embedding")
    except Exception as exc:
        logger.debug("embedding health degradation sync skipped: %s", exc)


def sync_compaction_acl_from_metrics() -> None:
    """Register compaction ACL degradations from runtime counters / recent skips."""
    total = 0
    try:
        from butler.ops.runtime_metrics import snapshot_global

        counters = snapshot_global().get("counters") or {}
        for key, value in counters.items():
            if key == "compaction_acl_degraded" or key.startswith("compaction_acl_degraded{"):
                total += int(value or 0)
    except Exception as exc:
        logger.debug("compaction acl metrics sync skipped: %s", exc)
    if total <= 0:
        try:
            from butler.core.best_effort import recent_best_effort_skips

            total = sum(
                1
                for _ts, path, _err in recent_best_effort_skips(10)
                if str(path).startswith("compaction_acl")
            )
        except Exception:
            pass
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
    try:
        from butler.mcp.config import load_mcp_servers, mcp_enabled, mcp_sdk_available
        from butler.registry.paths import default_mcp_config_path
    except Exception as exc:
        logger.debug("mcp degradation sync import skipped: %s", exc)
        return

    if not mcp_enabled():
        if default_mcp_config_path().is_file():
            register_degradation("mcp", "已配置但 BUTLER_MCP_ENABLED 未开")
        else:
            clear_degradation("mcp")
        return

    if not mcp_sdk_available():
        register_degradation("mcp", "缺少 MCP SDK (pip install butler-system[mcp])")
        return

    sk = str(session_key or "gateway:warmup").strip() or "gateway:warmup"
    try:
        from butler.mcp.manager import get_manager

        mgr = get_manager()
        mgr.ensure_connected(sk, workspace=None)
    except Exception as exc:
        logger.debug("mcp warm-up connect skipped: %s", exc)

    try:
        from butler.mcp.manager import get_manager

        statuses = get_manager().status_snapshot(sk)
    except Exception as exc:
        logger.debug("mcp status snapshot skipped: %s", exc)
        return

    if not statuses:
        try:
            cfg_count = len(load_mcp_servers(workspace=None))
        except Exception:
            cfg_count = 0
        if cfg_count > 0:
            register_degradation("mcp", f"{cfg_count} 个 server 均未连接")
        else:
            clear_degradation("mcp")
        return

    down = [st for st in statuses if not st.connected]
    if down:
        register_degradation("mcp", f"{len(down)}/{len(statuses)} 个 server 不可用")
    else:
        clear_degradation("mcp")


def enrich_stats_with_live_mcp(
    stats: dict[str, Any],
    *,
    session_key: str = "",
) -> dict[str, Any]:
    """Attach live MCP snapshot for owner brief / diagnostic sync (ENG-8)."""
    out = dict(stats)
    try:
        from butler.mcp.config import mcp_enabled

        if not mcp_enabled():
            return out
        from butler.mcp.manager import get_manager

        sk = str(session_key or "").strip() or "gateway:diagnostic"
        statuses = get_manager().status_snapshot(sk)
        down = [st for st in statuses if not st.connected]
        if down:
            out["mcp_degraded"] = [
                str(getattr(st, "name", None) or getattr(st, "server_id", "?"))
                for st in down
            ]
        elif statuses:
            out.pop("mcp_degraded", None)
    except Exception as exc:
        logger.debug("live mcp enrichment skipped: %s", exc)
    return out


def refresh_degradations_for_owner_brief(
    orchestrator: Any,
    *,
    session_key: str = "",
    health: dict[str, Any] | None = None,
) -> str | None:
    """Sync memory + MCP into registry; return one brief line for Owner /诊断."""
    try:
        sync_compaction_acl_from_metrics()
        from butler.ops.health_report import collect_mem_stats_for_health

        stats = collect_mem_stats_for_health(
            orchestrator, str(session_key or "").strip(), health
        )
        stats = enrich_stats_with_live_mcp(stats, session_key=session_key)
        sync_memory_degradations_from_stats(stats)
        return format_brief_line()
    except Exception as exc:
        logger.debug("refresh degradations skipped: %s", exc)
        return None


def _set_component_gauge(component: str, *, active: bool) -> None:
    try:
        from butler.ops.runtime_metrics import set_gauge

        set_gauge(
            "degradation_active",
            1.0 if active else 0.0,
            labels={"component": str(component or "?")[:48]},
        )
    except Exception as exc:
        logger.debug("degradation component gauge skipped: %s", exc)


def _sync_metrics() -> None:
    try:
        from butler.ops.runtime_metrics import set_gauge

        with _LOCK:
            n = len(_REGISTRY)
            components = list(_REGISTRY.keys())
        set_gauge("degradation_active", float(n))
        for comp in components:
            _set_component_gauge(comp, active=True)
    except Exception as exc:
        logger.debug("degradation metrics sync skipped: %s", exc)


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
