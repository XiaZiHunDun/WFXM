"""Persist memory effectiveness metrics (D2-4/D2-5) to ~/.butler/metrics/."""

from __future__ import annotations

import time

from butler.memory_settings import resolve_memory_config
from pathlib import Path

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
    from butler.memory.metrics_persist_ops import load_collector_from_file_safe

    load_collector_from_file_safe(path)


def flush_memory_metrics(*, force: bool = False) -> None:
    """Write collector state to disk (rate-limited unless force)."""
    global _last_flush
    if not metrics_enabled():
        return
    now = time.time()
    if not force and (now - _last_flush) < _FLUSH_INTERVAL_SEC:
        return
    from butler.memory.metrics_persist_ops import save_collector_to_file_safe

    save_collector_to_file_safe(metrics_path())
    _last_flush = now


def format_effectiveness_lines() -> list[str]:
    """S_w / H_1 / E_d lines for /诊断 (D2-4/D2-5/D2-6)."""
    from butler.memory.metrics_persist_ops import format_effectiveness_lines_safe

    return format_effectiveness_lines_safe()
