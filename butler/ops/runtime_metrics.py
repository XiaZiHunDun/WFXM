"""In-process runtime metrics (Prometheus-style naming, zero external deps)."""

from __future__ import annotations

import hashlib
import threading
from collections import deque
from typing import Any

_LOCK = threading.Lock()
_COUNTERS: dict[tuple[str, tuple[tuple[str, str], ...]], int] = {}
_GAUGES: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
_HISTOGRAMS: dict[tuple[str, tuple[tuple[str, str], ...]], deque[float]] = {}
_HISTOGRAM_MAXLEN = 64
_SESSION_LABEL = "session"


def _session_tag(session_key: str) -> str:
    raw = str(session_key or "").strip()
    if not raw:
        return ""
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:8]
    return f"s:{digest}"


def _label_key(labels: dict[str, str] | None, *, session_key: str = "") -> tuple[tuple[str, str], ...]:
    merged: dict[str, str] = {}
    if labels:
        for key, value in labels.items():
            if key and value is not None:
                merged[str(key)] = str(value)
    tag = _session_tag(session_key)
    if tag:
        merged[_SESSION_LABEL] = tag
    if not merged:
        return ()
    return tuple(sorted(merged.items()))


def _metric_key(name: str, labels: dict[str, str] | None = None, *, session_key: str = "") -> tuple[str, tuple[tuple[str, str], ...]]:
    return (str(name), _label_key(labels, session_key=session_key))


def inc(
    name: str,
    value: int = 1,
    *,
    labels: dict[str, str] | None = None,
    session_key: str = "",
) -> None:
    if value <= 0:
        return
    key = _metric_key(name, labels, session_key=session_key)
    with _LOCK:
        _COUNTERS[key] = _COUNTERS.get(key, 0) + int(value)


def set_gauge(
    name: str,
    value: float,
    *,
    labels: dict[str, str] | None = None,
    session_key: str = "",
) -> None:
    key = _metric_key(name, labels, session_key=session_key)
    with _LOCK:
        _GAUGES[key] = float(value)


def observe_ms(
    name: str,
    milliseconds: float,
    *,
    labels: dict[str, str] | None = None,
    session_key: str = "",
) -> None:
    if milliseconds < 0:
        return
    key = _metric_key(name, labels, session_key=session_key)
    with _LOCK:
        bucket = _HISTOGRAMS.setdefault(key, deque(maxlen=_HISTOGRAM_MAXLEN))
        bucket.append(float(milliseconds))


def counter_value(
    name: str,
    *,
    labels: dict[str, str] | None = None,
    session_key: str = "",
) -> int:
    key = _metric_key(name, labels, session_key=session_key)
    with _LOCK:
        return int(_COUNTERS.get(key, 0))


def _percentile(values: list[float], pct: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    rank = max(0, min(len(ordered) - 1, int(round((pct / 100.0) * (len(ordered) - 1)))))
    return ordered[rank]


def _histogram_stats(key: tuple[str, tuple[tuple[str, str], ...]]) -> dict[str, Any] | None:
    with _LOCK:
        bucket = _HISTOGRAMS.get(key)
        if not bucket:
            return None
        values = list(bucket)
    count = len(values)
    return {
        "count": count,
        "p50_ms": _percentile(values, 50),
        "p95_ms": _percentile(values, 95),
        "max_ms": max(values),
    }


def _labels_to_str(label_tuple: tuple[tuple[str, str], ...]) -> str:
    if not label_tuple:
        return ""
    return ",".join(f"{k}={v}" for k, v in label_tuple)


def _is_session_scoped(label_tuple: tuple[tuple[str, str], ...], session_tag: str) -> bool:
    return bool(session_tag) and any(k == _SESSION_LABEL and v == session_tag for k, v in label_tuple)


def reset_session(session_key: str) -> None:
    tag = _session_tag(session_key)
    if not tag:
        return
    with _LOCK:
        for store in (_COUNTERS, _GAUGES):
            for key in list(store):
                if _is_session_scoped(key[1], tag):
                    store.pop(key, None)
        for key in list(_HISTOGRAMS):
            if _is_session_scoped(key[1], tag):
                _HISTOGRAMS.pop(key, None)


def reset_global() -> None:
    with _LOCK:
        _COUNTERS.clear()
        _GAUGES.clear()
        _HISTOGRAMS.clear()


def reset_counters_named(name: str, *, session_key: str | None = None) -> None:
    """Drop counters for one metric (all sessions or one session tag)."""
    metric = str(name)
    tag = _session_tag(session_key or "") if session_key else ""
    with _LOCK:
        for key in list(_COUNTERS):
            if key[0] != metric:
                continue
            if session_key:
                if _is_session_scoped(key[1], tag):
                    _COUNTERS.pop(key, None)
            else:
                _COUNTERS.pop(key, None)


def snapshot_global() -> dict[str, Any]:
    """Aggregate process-wide counters/histograms (exclude per-session label)."""
    counters: dict[str, int] = {}
    histograms: dict[str, dict[str, Any]] = {}
    gauges: dict[str, float] = {}
    with _LOCK:
        counter_items = list(_COUNTERS.items())
        gauge_items = list(_GAUGES.items())
        hist_keys = list(_HISTOGRAMS.keys())
    for (name, label_tuple), value in counter_items:
        if any(k == _SESSION_LABEL for k, _ in label_tuple):
            continue
        key = name if not label_tuple else f"{name}{{{_labels_to_str(label_tuple)}}}"
        counters[key] = counters.get(key, 0) + int(value)
    for (name, label_tuple), value in gauge_items:
        if any(k == _SESSION_LABEL for k, _ in label_tuple):
            continue
        key = name if not label_tuple else f"{name}{{{_labels_to_str(label_tuple)}}}"
        gauges[key] = float(value)
    for key in hist_keys:
        name, label_tuple = key
        if any(k == _SESSION_LABEL for k, _ in label_tuple):
            continue
        stats = _histogram_stats(key)
        if not stats:
            continue
        hist_key = name if not label_tuple else f"{name}{{{_labels_to_str(label_tuple)}}}"
        histograms[hist_key] = stats
    return {"counters": counters, "gauges": gauges, "histograms": histograms}


def snapshot_session(session_key: str) -> dict[str, Any]:
    tag = _session_tag(session_key)
    if not tag:
        return {"counters": {}, "gauges": {}, "histograms": {}}
    counters: dict[str, int] = {}
    gauges: dict[str, float] = {}
    histograms: dict[str, dict[str, Any]] = {}
    with _LOCK:
        counter_items = list(_COUNTERS.items())
        gauge_items = list(_GAUGES.items())
        hist_keys = list(_HISTOGRAMS.keys())
    for (name, label_tuple), value in counter_items:
        if not _is_session_scoped(label_tuple, tag):
            continue
        plain_labels = tuple((k, v) for k, v in label_tuple if k != _SESSION_LABEL)
        key = name if not plain_labels else f"{name}{{{_labels_to_str(plain_labels)}}}"
        counters[key] = counters.get(key, 0) + int(value)
    for (name, label_tuple), value in gauge_items:
        if not _is_session_scoped(label_tuple, tag):
            continue
        plain_labels = tuple((k, v) for k, v in label_tuple if k != _SESSION_LABEL)
        key = name if not plain_labels else f"{name}{{{_labels_to_str(plain_labels)}}}"
        gauges[key] = float(value)
    for key in hist_keys:
        name, label_tuple = key
        if not _is_session_scoped(label_tuple, tag):
            continue
        stats = _histogram_stats(key)
        if not stats:
            continue
        plain_labels = tuple((k, v) for k, v in label_tuple if k != _SESSION_LABEL)
        hist_key = name if not plain_labels else f"{name}{{{_labels_to_str(plain_labels)}}}"
        histograms[hist_key] = stats
    return {"counters": counters, "gauges": gauges, "histograms": histograms}


def _format_histogram_line(key: str, stats: dict[str, Any]) -> str:
    p50 = stats.get("p50_ms")
    p95 = stats.get("p95_ms")
    count = stats.get("count", 0)
    if p50 is None:
        return f"  {key}: n={count}"
    p50_s = f"{p50:.0f}ms" if p50 < 10_000 else f"{p50 / 1000:.1f}s"
    if p95 is None:
        return f"  {key}: n={count} p50={p50_s}"
    p95_s = f"{p95:.0f}ms" if p95 < 10_000 else f"{p95 / 1000:.1f}s"
    return f"  {key}: n={count} p50={p50_s} p95={p95_s}"


def format_metrics_diagnostic_lines(*, session_key: str = "") -> list[str]:
    """Human-readable metrics block for ``/诊断``."""
    lines: list[str] = ["运行指标（进程累计）:"]
    global_snap = snapshot_global()
    counters = global_snap.get("counters") or {}
    gauges = global_snap.get("gauges") or {}
    histograms = global_snap.get("histograms") or {}
    if not counters and not gauges and not histograms:
        lines.append("  （暂无采样）")
    else:
        for key in sorted(counters):
            lines.append(f"  {key}: {counters[key]}")
        for key in sorted(gauges):
            val = gauges[key]
            if key == "gateway_sessions":
                lines.append(f"  {key}: {int(val)}")
            else:
                lines.append(f"  {key}: {val:g}")
        for key in sorted(histograms):
            lines.append(_format_histogram_line(key, histograms[key]))

    if session_key and str(session_key).strip():
        session_snap = snapshot_session(session_key)
        sc = session_snap.get("counters") or {}
        sg = session_snap.get("gauges") or {}
        sh = session_snap.get("histograms") or {}
        if sc or sg or sh:
            lines.append("运行指标（本会话）:")
            for key in sorted(sc):
                lines.append(f"  {key}: {sc[key]}")
            for key in sorted(sg):
                lines.append(f"  {key}: {sg[key]:g}")
            for key in sorted(sh):
                lines.append(_format_histogram_line(key, sh[key]))
    return lines


def publish_gateway_session_gauges(*, session_count: int, active_turns: int) -> None:
    set_gauge("gateway_sessions", float(session_count))
    set_gauge("gateway_active_turns", float(active_turns))
