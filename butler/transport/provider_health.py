"""Provider circuit breaker + failover ordering (CC Switch subset)."""

from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass
from typing import Any

from butler.env_parse import env_truthy
from butler.transport.fallback import FallbackEntry

_STATE_LOCK = threading.Lock()
_STATE: dict[str, "_CircuitState"] = {}


@dataclass
class _CircuitState:
    failures: int = 0
    last_failure: float = 0.0
    open_until: float = 0.0


def provider_circuit_enabled() -> bool:
    return env_truthy("BUTLER_PROVIDER_CIRCUIT", default=True)


def _failure_threshold() -> int:
    try:
        return max(2, int(os.getenv("BUTLER_PROVIDER_CIRCUIT_FAILURES", "3")))
    except ValueError:
        return 3


def _open_seconds() -> float:
    try:
        return max(30.0, float(os.getenv("BUTLER_PROVIDER_CIRCUIT_OPEN_SECONDS", "120")))
    except ValueError:
        return 120.0


def provider_key(provider: str, model: str) -> str:
    return f"{provider or '?'}:{model or '?'}"


def _get_state(key: str) -> _CircuitState:
    with _STATE_LOCK:
        st = _STATE.get(key)
        if st is None:
            st = _CircuitState()
            _STATE[key] = st
        return st


def is_circuit_open(provider: str, model: str) -> bool:
    if not provider_circuit_enabled():
        return False
    key = provider_key(provider, model)
    st = _get_state(key)
    now = time.time()
    if st.open_until and now < st.open_until:
        return True
    if st.open_until and now >= st.open_until:
        st.open_until = 0.0
        st.failures = 0
    return False


def record_provider_success(provider: str, model: str) -> None:
    if not provider_circuit_enabled():
        return
    key = provider_key(provider, model)
    with _STATE_LOCK:
        st = _STATE.get(key)
        if st is not None:
            st.failures = 0
            st.open_until = 0.0


def record_provider_failure(provider: str, model: str) -> None:
    if not provider_circuit_enabled():
        return
    key = provider_key(provider, model)
    st = _get_state(key)
    now = time.time()
    with _STATE_LOCK:
        st.failures += 1
        st.last_failure = now
        if st.failures >= _failure_threshold():
            st.open_until = now + _open_seconds()


def filter_fallback_chain(chain: list[FallbackEntry]) -> list[FallbackEntry]:
    """Drop entries whose circuit is open; preserve order."""
    if not provider_circuit_enabled():
        return chain
    out: list[FallbackEntry] = []
    for entry in chain:
        if is_circuit_open(entry.provider, entry.model):
            continue
        out.append(entry)
    return out or chain


def failover_list_from_env() -> list[tuple[str, str]]:
    raw = os.getenv("BUTLER_PROVIDER_FAILOVER", "").strip()
    if not raw:
        return []
    pairs: list[tuple[str, str]] = []
    for part in raw.split(","):
        piece = part.strip()
        if not piece:
            continue
        if "/" in piece:
            prov, model = piece.split("/", 1)
            pairs.append((prov.strip(), model.strip()))
        else:
            pairs.append((piece, ""))
    return pairs


def format_circuit_diagnostic_lines() -> list[str]:
    if not provider_circuit_enabled():
        return []
    snap = health_snapshot()
    if not snap:
        return []
    lines = ["供应商熔断:"]
    for row in snap[:6]:
        key = row.get("provider_model") or "?"
        open_flag = row.get("open")
        fails = row.get("failures", 0)
        lines.append(f"  {key}: failures={fails} open={open_flag}")
    return lines


def health_snapshot() -> list[dict[str, Any]]:
    now = time.time()
    with _STATE_LOCK:
        items = []
        for key, st in sorted(_STATE.items()):
            items.append(
                {
                    "provider_model": key,
                    "failures": st.failures,
                    "open": bool(st.open_until and now < st.open_until),
                    "open_until": st.open_until if st.open_until else None,
                }
            )
    return items
