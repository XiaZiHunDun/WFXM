"""Best-effort forwarding shims for the metrics sink (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.core.best_effort import safe_best_effort
from butler.core.metrics_sink import get_default_sink


def observe_ms_safe(name: str, milliseconds: float) -> None:
    safe_best_effort(
        lambda: get_default_sink().observe_ms(name, milliseconds),
        label="metrics_sink.observe_ms",
        default=None,
    )


def inc_safe(
    name: str,
    value: int = 1,
    *,
    labels: dict[str, str] | None = None,
    session_key: str = "",
) -> None:
    def _run() -> None:
        get_default_sink().inc(
            name,
            value,
            labels=labels,
            session_key=session_key,
        )

    safe_best_effort(_run, label="metrics_sink.inc", default=None)


def record_event_safe(
    name: str,
    fields: dict[str, Any],
    *,
    session_key: str = "",
) -> None:
    def _run() -> None:
        get_default_sink().record_event(name, fields, session_key=session_key)

    safe_best_effort(_run, label="metrics_sink.record_event", default=None)
