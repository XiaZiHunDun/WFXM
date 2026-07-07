"""Best-effort degradation registry probes and sync helpers (P0-A)."""

from __future__ import annotations

import logging
from typing import Any

from butler.core.best_effort import recent_best_effort_skips, safe_best_effort
from butler.mcp.config import load_mcp_servers, mcp_enabled, mcp_sdk_available
from butler.mcp.manager import get_manager
from butler.memory.embedding import HashingEmbedder, get_embedder
from butler.memory.semantic_config import embedding_model_name, embedding_provider_name
from butler.ops.embedding_health import check_embedding_recall
from butler.ops.runtime_metrics import set_gauge, snapshot_global
from butler.registry.paths import default_mcp_config_path

logger = logging.getLogger(__name__)


def best_effort_skip_total_safe() -> int:
    def _run() -> int:
        snap = snapshot_global()
        counters = snap.get("counters") if isinstance(snap, dict) else None
        if not isinstance(counters, dict):
            return 0
        return sum(
            int(value or 0)
            for key, value in counters.items()
            if str(key).startswith("best_effort_skip")
        )

    result = safe_best_effort(
        _run,
        label="degradation_registry.best_effort_skip_total",
        default=0,
    )
    return int(result or 0)


def append_recent_best_effort_skip_lines(lines: list[str]) -> None:
    def _run() -> None:
        recent = recent_best_effort_skips(5)
        for _ts, path, err in recent:
            lines.append(f"    · {path}: {err[:100]}")

    safe_best_effort(_run, label="degradation_registry.recent_skips", default=None)


def sync_embedding_degradation_light_safe() -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import clear_degradation, register_degradation

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

    safe_best_effort(_run, label="degradation_registry.embedding_light", default=None)


def sync_embedding_degradation_from_health_check_safe(*, min_recall: float = 0.5) -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import clear_degradation, register_degradation

        report = check_embedding_recall(min_recall=min_recall)
        if report.degraded:
            register_degradation("embedding", report.message[:200])
        elif not report.ok(min_recall=min_recall):
            register_degradation(
                "embedding",
                f"Recall@3 偏低: {report.message[:160]}",
            )
        else:
            clear_degradation("embedding")

    safe_best_effort(
        _run,
        label="degradation_registry.embedding_health",
        default=None,
    )


def compaction_acl_counter_total_safe() -> int:
    def _run() -> int:
        counters = snapshot_global().get("counters") or {}
        total = 0
        for key, value in counters.items():
            if key == "compaction_acl_degraded" or key.startswith("compaction_acl_degraded{"):
                total += int(value or 0)
        return total

    result = safe_best_effort(
        _run,
        label="degradation_registry.compaction_acl_metrics",
        default=0,
    )
    return int(result or 0)


def recent_compaction_acl_skip_count_safe() -> int:
    def _run() -> int:
        return sum(
            1
            for _ts, path, _err in recent_best_effort_skips(10)
            if str(path).startswith("compaction_acl")
        )

    result = safe_best_effort(
        _run,
        label="degradation_registry.compaction_acl_skips",
        default=0,
    )
    return int(result or 0)


def sync_mcp_degradations_at_startup_safe(*, session_key: str = "gateway:warmup") -> None:
    def _run() -> None:
        from butler.ops.degradation_registry import clear_degradation, register_degradation

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
        mgr = get_manager()
        safe_best_effort(
            lambda: mgr.ensure_connected(sk, workspace=None),
            label="degradation_registry.mcp_warmup",
            default=None,
        )
        statuses = mgr.status_snapshot(sk)
        if not statuses:
            cfg_count = len(load_mcp_servers(workspace=None))
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

    safe_best_effort(_run, label="degradation_registry.mcp_startup", default=None)


def enrich_stats_with_live_mcp_safe(
    stats: dict[str, Any],
    *,
    session_key: str = "",
) -> dict[str, Any]:
    out = dict(stats)

    def _run() -> None:
        if not mcp_enabled():
            return
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

    safe_best_effort(_run, label="degradation_registry.live_mcp", default=None)
    return out


def refresh_degradations_for_owner_brief_safe(
    orchestrator: Any,
    *,
    session_key: str = "",
    health: dict[str, Any] | None = None,
) -> str | None:
    def _run() -> str | None:
        from butler.ops.degradation_registry import (
            format_brief_line,
            sync_compaction_acl_from_metrics,
            sync_memory_degradations_from_stats,
        )
        from butler.ops.health_report import collect_mem_stats_for_health

        sync_compaction_acl_from_metrics()
        stats = collect_mem_stats_for_health(
            orchestrator, str(session_key or "").strip(), health
        )
        stats = enrich_stats_with_live_mcp_safe(stats, session_key=session_key)
        sync_memory_degradations_from_stats(stats)
        line = format_brief_line()
        return str(line) if line is not None else None

    result = safe_best_effort(
        _run,
        label="degradation_registry.owner_brief_refresh",
        default=None,
    )
    return result if isinstance(result, str) else None


def set_component_gauge_safe(component: str, *, active: bool) -> None:
    def _run() -> None:
        set_gauge(
            "degradation_active",
            1.0 if active else 0.0,
            labels={"component": str(component or "?")[:48]},
        )

    safe_best_effort(_run, label="degradation_registry.component_gauge", default=None)


def sync_degradation_metrics_safe(registry: dict[str, Any]) -> None:
    def _run() -> None:
        n = len(registry)
        components = list(registry.keys())
        set_gauge("degradation_active", float(n))
        for comp in components:
            set_component_gauge_safe(comp, active=True)

    safe_best_effort(_run, label="degradation_registry.metrics_sync", default=None)
