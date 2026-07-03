"""Stream probe execution best-effort helpers (P0-A)."""

from __future__ import annotations

import logging
import time
from typing import Any

logger = logging.getLogger(__name__)


def execute_stream_probe_safe(orchestrator: Any, *, t0: float) -> dict[str, Any]:
    """Run one minimal completion; return probe row (ok or fail)."""
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
        return {
            "ok": ok,
            "latency_ms": round(ms, 1),
            "provider": creds.get("provider") or "",
            "model": creds.get("model") or "",
        }
    except Exception as exc:
        ms = (time.perf_counter() - t0) * 1000.0
        logger.debug("stream probe failed: %s", exc)
        return {"ok": False, "latency_ms": round(ms, 1), "error": str(exc)[:200]}
