"""Persist memory effectiveness metrics (D2-4/D2-5) to ~/.butler/metrics/."""

from __future__ import annotations

import logging
import time

from butler.memory_settings import resolve_memory_config
from pathlib import Path

logger = logging.getLogger(__name__)

_FLUSH_INTERVAL_SEC = 60.0
_last_flush: float = 0.0
_loaded_once: bool = False


def metrics_enabled() -> bool:
    return resolve_memory_config().metrics_persist


def metrics_path() -> Path:
    from butler.config import get_butler_home

    return get_butler_home() / "metrics" / "memory_metrics.json"


def load_persisted_metrics() -> None:
    """Load aggregate session metrics once per process (best-effort)."""
    global _loaded_once
    if _loaded_once or not metrics_enabled():
        return
    _loaded_once = True
    path = metrics_path()
    if not path.is_file():
        return
    try:
        from butler.memory.memory_metrics import get_collector

        get_collector().load_from_file(path)
    except Exception as exc:
        logger.debug("load persisted memory metrics skipped: %s", exc)


def flush_memory_metrics(*, force: bool = False) -> None:
    """Write collector state to disk (rate-limited unless force)."""
    global _last_flush
    if not metrics_enabled():
        return
    now = time.time()
    if not force and (now - _last_flush) < _FLUSH_INTERVAL_SEC:
        return
    try:
        from butler.memory.memory_metrics import get_collector

        get_collector().save_to_file(metrics_path())
        _last_flush = now
    except Exception as exc:
        logger.debug("flush memory metrics skipped: %s", exc)


def format_effectiveness_lines() -> list[str]:
    """S_w / H_1 / E_d lines for /诊断 (D2-4/D2-5/D2-6)."""
    try:
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
        if metrics_enabled():
            lines.append(f"  持久化: {metrics_path()}")
        return lines
    except Exception as exc:
        logger.debug("format effectiveness lines skipped: %s", exc)
        return []
