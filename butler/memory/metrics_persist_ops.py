"""Memory metrics persistence best-effort helpers (P0-A)."""

from __future__ import annotations

from pathlib import Path

from butler.core.best_effort import safe_best_effort


def load_collector_from_file_safe(path: Path) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector

        get_collector().load_from_file(path)

    safe_best_effort(_run, label="metrics_persist.load", default=None)


def save_collector_to_file_safe(path: Path) -> None:
    def _run() -> None:
        from butler.memory.memory_metrics import get_collector

        get_collector().save_to_file(path)

    safe_best_effort(_run, label="metrics_persist.flush", default=None)


def format_effectiveness_lines_safe() -> list[str]:
    def _run() -> list[str]:
        from butler.memory.memory_metrics import get_collector

        agg = get_collector().get_aggregate()
        if agg.total_sessions == 0 and agg.total_prefetch_turns == 0:
            return []
        comp = agg.to_dict().get("computed", {})
        lines = [
            "记忆效果度量 (L2):",
            f"  S_w 写入存活率: {comp.get('write_survival_rate', 1.0):.0%}"
            f" ({agg.total_write_probes_recalled}/{agg.total_write_probes or agg.total_writes_successful}"
            f" probes)",
            f"  H_1 首轮命中率: {comp.get('first_turn_hit_rate', 1.0):.0%}"
            f" ({agg.total_prefetch_hits}/{agg.total_prefetch_turns} turns)",
            f"  E_d 衰减误杀率: {comp.get('decay_error_rate', 0.0):.0%}"
            f" ({agg.total_decay_kills}/{agg.total_decay_evals} evals)",
        ]
        if agg.total_retrieval_total > 0:
            lines.append(
                f"  P_r 预取引用率: {comp.get('retrieval_precision', 1.0):.0%}"
                f" ({agg.total_retrieval_used}/{agg.total_retrieval_total} items)"
            )
        from butler.memory.metrics_persist import metrics_enabled, metrics_path

        if metrics_enabled():
            lines.append(f"  持久化: {metrics_path()}")
        return lines

    result = safe_best_effort(
        _run,
        label="metrics_persist.effectiveness_lines",
        default=[],
    )
    return list(result) if isinstance(result, list) else []
