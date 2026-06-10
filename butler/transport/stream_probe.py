"""Optional streaming first-chunk probe for /诊断 (cc-switch subset)."""

from __future__ import annotations

import logging
import threading
import time
from typing import Any

from butler.core.metrics_sink import observe_ms
from butler.env_parse import env_truthy

logger = logging.getLogger(__name__)

_PROBE_LOCK = threading.Lock()
_LAST_PROBE: dict[str, Any] = {}


def stream_probe_enabled() -> bool:
    return env_truthy("BUTLER_STREAM_PROBE", default=False)


def last_stream_probe() -> dict[str, Any]:
    with _PROBE_LOCK:
        return dict(_LAST_PROBE)


def run_stream_probe(orchestrator: Any) -> dict[str, Any]:
    """Lightweight ping: one minimal chat completion when enabled."""
    if not stream_probe_enabled():
        return {"skipped": True, "reason": "disabled"}
    t0 = time.perf_counter()
    try:
        creds = orchestrator._model_credentials("butler")
        from butler.transport.llm_client import LLMClient

        client = LLMClient(
            provider=creds.get("provider") or "",
            model=creds.get("model") or "",
            api_key=creds.get("api_key") or "",
            base_url=creds.get("base_url") or "",
        )
        resp = client.complete(
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=4,
        )
        ms = (time.perf_counter() - t0) * 1000.0
        ok = bool(getattr(resp, "content", None) or getattr(resp, "text", None))
        row = {
            "ok": ok,
            "latency_ms": round(ms, 1),
            "provider": creds.get("provider") or "",
            "model": creds.get("model") or "",
        }
        with _PROBE_LOCK:
            _LAST_PROBE.clear()
            _LAST_PROBE.update(row)
        observe_ms("stream_probe_latency_ms", ms)
        return dict(row)
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        row = {"ok": False, "latency_ms": round(ms, 1), "error": str(exc)[:200]}
        logger.debug("stream probe failed: %s", exc)
        with _PROBE_LOCK:
            _LAST_PROBE.clear()
            _LAST_PROBE.update(row)
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
