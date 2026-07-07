"""Turn-scoped health diagnostic Protocol — health_report without importing turn module."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol, runtime_checkable

from butler.ops.health_report_input import HealthReportInput


@runtime_checkable
class HealthDiagnosticPort(Protocol):
    """Per-turn ``/诊断`` line block."""

    def turn_diagnostic_lines(
        self,
        inp: HealthReportInput,
        *,
        hook_lines_fn: Callable[[str, dict[str, Any] | None], list[str]],
    ) -> list[str]: ...


__all__ = ["HealthDiagnosticPort"]
