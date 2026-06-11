"""Shared types for B9 LLM delegate benchmarks."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Callable


class B9Mode(str, Enum):
    ORACLE = "oracle"
    LIVE = "live"


@dataclass
class B9TaskSpec:
    task_id: str
    description: str
    delegate_prompt: str
    setup: Callable[[Path], None]
    verify: Callable[[Path], tuple[bool, str]]
    oracle_apply: Callable[[Path], None]
    expect_pass: bool = True
    tags: tuple[str, ...] = ()


@dataclass
class B9Result:
    task_id: str
    description: str
    passed: bool
    mode: str
    score: float = 0.0
    failure_reasons: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    elapsed_seconds: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "description": self.description,
            "passed": self.passed,
            "mode": self.mode,
            "score": self.score,
            "failure_reasons": self.failure_reasons,
            "tools_used": self.tools_used,
            "elapsed_seconds": round(self.elapsed_seconds, 3),
        }


@dataclass
class B9Report:
    results: list[B9Result] = field(default_factory=list)
    mode: str = B9Mode.ORACLE.value

    @property
    def total(self) -> int:
        return len(self.results)

    @property
    def passed(self) -> int:
        return sum(1 for r in self.results if r.passed)

    @property
    def pass_rate(self) -> float:
        return self.passed / self.total if self.total else 0.0


__all__ = [
    "B9Mode",
    "B9Report",
    "B9Result",
    "B9TaskSpec",
]
