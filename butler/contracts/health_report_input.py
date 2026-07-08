"""Turn-scoped health diagnostic input view (contracts — no ops/core imports)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class HealthReportInput:
    session_key: str
    health: dict[str, Any] | None
    tool_summary: dict[str, Any]
    mem_stats: dict[str, Any]
    orchestrator: Any


__all__ = ["HealthReportInput"]
