"""Eval integration Port contracts (MOD-2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable


@dataclass
class SuiteRunResult:
    """Result of one eval suite execution."""

    suite_id: str
    ok: bool
    layer: str = ""
    metrics: dict[str, Any] = field(default_factory=dict)
    sink_refs: dict[str, str] = field(default_factory=dict)
    error: str = ""


@runtime_checkable
class EvalSuitePort(Protocol):
    """Runnable eval suite (L-A..L-D)."""

    @property
    def suite_id(self) -> str: ...

    @property
    def layer(self) -> str: ...

    def run(self, *, warn_only: bool = False) -> SuiteRunResult: ...


@runtime_checkable
class ScoreSinkPort(Protocol):
    """Score / report backend (multi-SSOT)."""

    @property
    def backend_id(self) -> str: ...

    def write_suite_result(self, result: SuiteRunResult, payload: dict[str, Any]) -> str: ...

    def read_latest(self, suite_id: str) -> dict[str, Any] | None: ...
