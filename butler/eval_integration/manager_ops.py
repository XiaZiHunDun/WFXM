"""Eval integration manager sink best-effort helpers (P0-A)."""

from __future__ import annotations

from typing import Any

from butler.contracts.eval_ports import ScoreSinkPort, SuiteRunResult


def write_suite_result_safe(
    sink: ScoreSinkPort,
    result: SuiteRunResult,
    payload: dict[str, Any],
) -> str:
    try:
        ref = sink.write_suite_result(result, payload)
        return str(ref) if ref else ""
    except Exception:
        return ""


def analyse_transform_signals_safe(*, tcr_rate: float) -> None:
    try:
        from butler.core.transform_feedback import analyse_transform_signals

        analyse_transform_signals(tcr_rate=tcr_rate)
    except Exception:
        pass
