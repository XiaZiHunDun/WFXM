"""Ops implementation of :class:`butler.core.metrics_sink.MetricsSink` (AP-5)."""

from __future__ import annotations

from typing import Any

from butler.ops import runtime_metrics


class RuntimeMetricsSink:
    """Forwards core metrics + structured events to ``runtime_metrics``."""

    def observe_ms(self, name: str, milliseconds: float) -> None:
        runtime_metrics.observe_ms(name, milliseconds)

    def inc(
        self,
        name: str,
        value: int = 1,
        *,
        labels: dict[str, str] | None = None,
        session_key: str = "",
    ) -> None:
        runtime_metrics.inc(
            name,
            value=value,
            labels=labels,
            session_key=session_key,
        )

    def record_event(
        self,
        name: str,
        fields: dict[str, Any],
        *,
        session_key: str = "",
    ) -> None:
        labels = {k: str(v) for k, v in fields.items() if k != "ts"}
        runtime_metrics.inc(f"structured_event_{name}", labels=labels, session_key=session_key)
        if name == "llm_api_call":
            runtime_metrics.observe_ms(
                "llm_api_call_ms",
                float(fields.get("duration_ms") or 0),
                labels={"status": str(fields.get("status") or "ok")},
                session_key=session_key,
            )
        if name == "retrieval" and fields.get("degraded"):
            runtime_metrics.inc(
                "retrieval_degraded",
                labels={"mode": str(fields.get("mode") or "")},
                session_key=session_key,
            )


def install_runtime_metrics_sink() -> None:
    from butler.core.metrics_sink import set_default_sink

    set_default_sink(RuntimeMetricsSink())


__all__ = ["RuntimeMetricsSink", "install_runtime_metrics_sink"]
