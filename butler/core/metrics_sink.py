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

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class MetricsSink(Protocol):
    """Protocol implemented by the ops side.

    Core / transport only see this contract; ops registers an implementation
    at runtime. Adding a new metric type = add a method here + a
    corresponding ops implementation.
    """

    def observe_ms(self, name: str, milliseconds: float) -> None: ...

    def inc(
        self,
        name: str,
        value: int = 1,
        *,
        labels: dict[str, str] | None = None,
        session_key: str = "",
    ) -> None: ...

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

    def inc(
        self,
        name: str,
        value: int = 1,
        *,
        labels: dict[str, str] | None = None,
        session_key: str = "",
    ) -> None:
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


def observe_ms(name: str, milliseconds: float) -> None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    from butler.core.metrics_sink_ops import observe_ms_safe

    observe_ms_safe(name, milliseconds)


def inc(
    name: str,
    value: int = 1,
    *,
    labels: dict[str, str] | None = None,
    session_key: str = "",
) -> None:
    """Forward to the registered sink; swallow exceptions (best-effort)."""
    from butler.core.metrics_sink_ops import inc_safe

    inc_safe(name, value, labels=labels, session_key=session_key)


def record_event(
    name: str,
    fields: dict[str, Any],
    *,
    session_key: str = "",
) -> None:
    """Forward structured event to the registered sink (best-effort)."""
    from butler.core.metrics_sink_ops import record_event_safe

    record_event_safe(name, fields, session_key=session_key)


__all__ = [
    "MetricsSink",
    "NullMetricsSink",
    "get_default_sink",
    "inc",
    "observe_ms",
    "record_event",
    "set_default_sink",
]
