"""Tests for HealthDiagnosticPort (Wave 4)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from butler.contracts.health_diagnostic_ports import HealthDiagnosticPort
from butler.contracts.health_diagnostic_registry import (
    get_health_diagnostic,
    set_health_diagnostic,
)
from butler.ops.health_report_input import HealthReportInput


class _StubDiagnostic:
    def turn_diagnostic_lines(
        self,
        inp: HealthReportInput,
        *,
        hook_lines_fn: Callable[[str, dict[str, Any] | None], list[str]],
    ) -> list[str]:
        return ["stub-turn", inp.session_key]


def test_health_diagnostic_port_registry():
    stub = _StubDiagnostic()
    set_health_diagnostic(stub)
    try:
        port = get_health_diagnostic()
        assert port is not None
        assert isinstance(port, HealthDiagnosticPort)
        inp = HealthReportInput(
            session_key="sk1",
            health={},
            tool_summary={},
            mem_stats={},
            orchestrator=object(),
        )
        lines = port.turn_diagnostic_lines(inp, hook_lines_fn=lambda _sk, _h: [])
        assert lines == ["stub-turn", "sk1"]
    finally:
        set_health_diagnostic(None)


def test_live_health_diagnostic_wired():
    import butler.ops.health_report_turn  # noqa: F401 — registers port

    port = get_health_diagnostic()
    assert port is not None
    assert isinstance(port, HealthDiagnosticPort)
