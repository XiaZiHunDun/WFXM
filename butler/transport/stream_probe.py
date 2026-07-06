"""Optional streaming first-chunk probe for /诊断 (cc-switch subset)."""

from __future__ import annotations

import threading
import time
from typing import Any

from butler.core.metrics_sink import observe_ms
from butler.env_parse import env_truthy

_PROBE_LOCK = threading.Lock()
_LAST_PROBE: dict[str, Any] = {}


def stream_probe_enabled() -> bool:
    return bool(env_truthy("BUTLER_STREAM_PROBE", default=False))


def last_stream_probe() -> dict[str, Any]:
    with _PROBE_LOCK:
        return dict(_LAST_PROBE)


def run_stream_probe(orchestrator: Any) -> dict[str, Any]:
    """Lightweight ping: one minimal chat completion when enabled."""
    if not stream_probe_enabled():
        return {"skipped": True, "reason": "disabled"}
    t0 = time.perf_counter()
    from butler.transport.stream_probe_ops import execute_stream_probe_safe

    row = execute_stream_probe_safe(orchestrator, t0=t0)
    with _PROBE_LOCK:
        _LAST_PROBE.clear()
        _LAST_PROBE.update(row)
    if row.get("ok"):
        observe_ms("stream_probe_latency_ms", float(row.get("latency_ms") or 0))
    return dict(row)


def format_stream_probe_lines() -> list[str]:
    with _PROBE_LOCK:
        snap = dict(_LAST_PROBE)
    if not snap:
        return []
    if snap.get("skipped"):
        return []
    ok = snap.get("ok")
    ms = snap.get("latency_ms")
    prov = snap.get("provider") or "?"
    return [f"流式探活: {'ok' if ok else 'fail'} {prov} {ms}ms"]


__all__ = [
    "format_stream_probe_lines",
    "last_stream_probe",
    "run_stream_probe",
    "stream_probe_enabled",
]
