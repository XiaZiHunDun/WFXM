"""Layering seam for runtime metrics (R1-9 fix).

The v4 architecture puts ``butler/core/`` below ``butler/ops/`` in the
dependency graph. ``butler/transport/stream_probe.py`` historically
lazy-imported ``butler.ops.runtime_metrics.observe_ms`` to record probe
latency. That coupling meant transport had to know about ops at runtime,
defeating the layering that lets CLI / Loop unit tests run without ops
being importable.

This module defines a :class:`MetricsSink` Protocol that ops implements;
core / transport modules call the convenience shims below instead of
touching ops directly.

The default sink is no-op (:class:`NullMetricsSink`); the ops side installs
a real implementation at runtime via :func:`set_default_sink`. Tests that
want to assert behaviour can swap in custom sinks the same way.

Mirrors the R1-3 ``butler/core/events_sink.py`` pattern (Protocol +
Null default + global setter + best-effort shims that swallow sink
exceptions so observability outages never break the caller).
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

logger = logging.getLogger(__name__)


@runtime_checkable
class MetricsSink(Protocol):
    """Protocol implemented by the ops side.

    Core / transport only see this contract; ops registers an implementation
    at runtime. Adding a new metric type = add a method here + a
    corresponding ops implementation.
    """

    def observe_ms(self, name: str, milliseconds: float) -> None: ...

    def inc(self, name: str, value: int = 1) -> None: ...

    def record_event(
        self,
        name: str,
        fields: dict[str, Any],
        *,
        session_key: str = "",
    ) -> None: ...


class NullMetricsSink:
    """No-op sink used when no ops is wired (CLI / unit tests / transport)."""

    def observe_ms(self, name: str, milliseconds: float) -> None:
        return None

    def inc(self, name: str, value: int = 1) -> None:
        return None

    def record_event(
        self,
        name: str,
        fields: dict[str, Any],
        *,
        session_key: str = "",
    ) -> None:
        return None


_SINK: MetricsSink = NullMetricsSink()


def set_default_sink(sink: MetricsSink | None) -> None:
    """Install the ops-side implementation. ``None`` resets to no-op."""
    global _SINK
    _SINK = sink if sink is not None else NullMetricsSink()


def get_default_sink() -> MetricsSink:
    """Return the currently registered sink (never ``None``; defaults to no-op)."""
    return _SINK


# ── Convenience shims used by core / transport modules ─────────────────────


def observe_ms(name: str, milliseconds: float) -> None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        _SINK.observe_ms(name, milliseconds)
    except Exception as exc:  # noqa: BLE001 — best-effort, never break the caller
        logger.debug("metrics_sink.observe_ms skipped: %s", exc)


def inc(name: str, value: int = 1) -> None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    try:
        _SINK.inc(name, value)
    except Exception as exc:  # noqa: BLE001 — best-effort, never break the caller
        logger.debug("metrics_sink.inc skipped: %s", exc)


def record_event(
    name: str,
    fields: dict[str, Any],
    *,
    session_key: str = "",
) -> None:
    """Forward structured event to the registered sink (best-effort)."""
    try:
        _SINK.record_event(name, fields, session_key=session_key)
    except Exception as exc:  # noqa: BLE001
        logger.debug("metrics_sink.record_event skipped: %s", exc)


__all__ = [
    "MetricsSink",
    "NullMetricsSink",
    "get_default_sink",
    "inc",
    "observe_ms",
    "record_event",
    "set_default_sink",
]
